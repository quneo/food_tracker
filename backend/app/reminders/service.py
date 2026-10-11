"""Personal reminders: schedule in the person's time zone, delivery through the outbox."""

import logging
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chat import outbox
from app.core.exceptions import DomainError, NotFound
from app.core.timeutil import from_local, local_now, to_local, zone
from app.database import utcnow
from app.reminders.models import Reminder

log = logging.getLogger(__name__)

# Older reminders (the server was down) are skipped instead of arriving late.
STALE = timedelta(minutes=45)
TEXTS = {
    "meal": "🍽 Не забудьте записать, что ели. Пришлите фото или напишите парой слов.",
    "weight": "⚖️ Время взвеситься. Пришлите вес, например: 82.4",
    "photo": "📸 Пора сделать фото прогресса. Пришлите фото с подписью «прогресс».",
}
KIND_NAMES = {"meal": "Записать питание", "weight": "Взвеситься", "photo": "Фото прогресса"}


def default_reminders(user) -> list[Reminder]:
    """Off by default; the person turns on what they need on the site or in the chat."""
    presets = [
        ("weight", "08:00", [1, 2, 3, 4, 5, 6, 7]),
        ("meal", "21:00", [1, 2, 3, 4, 5, 6, 7]),
        ("photo", "10:00", [7]),
    ]
    return [
        Reminder(user_id=user.id, kind=kind, time=at, days=days, enabled=False)
        for kind, at, days in presets
    ]


def parse_time(text: str) -> time:
    try:
        hours, minutes = text.split(":")
        return time(int(hours), int(minutes))
    except ValueError:
        raise DomainError("Время в формате ЧЧ:ММ, например 08:30") from None


def next_run(reminder: Reminder, tz_name: str, after: datetime | None = None) -> datetime | None:
    """The next moment (naive UTC) strictly after `after` on one of the reminder's days."""
    if not reminder.enabled or not reminder.days:
        return None
    tz = zone(tz_name)
    at = parse_time(reminder.time)
    after = after or utcnow()
    start = to_local(after, tz).date()
    for offset in range(8):
        day = start + timedelta(days=offset)
        if day.isoweekday() not in reminder.days:
            continue
        candidate = from_local(datetime.combine(day, at), tz)
        if candidate > after:
            return candidate
    return None


def reschedule(reminder: Reminder, tz_name: str):
    reminder.next_run_at = next_run(reminder, tz_name)


def text(reminder: Reminder) -> str:
    if reminder.kind == "custom":
        return f"⏰ {reminder.text or 'Напоминание'}"
    return TEXTS[reminder.kind]


def describe(reminder: Reminder) -> str:
    days = sorted(reminder.days)
    names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    when = (
        "каждый день"
        if days == [1, 2, 3, 4, 5, 6, 7]
        else "по будням"
        if days == [1, 2, 3, 4, 5]
        else ", ".join(names[d - 1] for d in days)
    )
    what = reminder.text if reminder.kind == "custom" else KIND_NAMES[reminder.kind]
    return f"{what}: {when} в {reminder.time}"


def owned(db: Session, reminder_id: int, user_id: int) -> Reminder:
    reminder = db.get(Reminder, reminder_id)
    if not reminder or reminder.user_id != user_id:
        raise NotFound("Напоминание не найдено")
    return reminder


def _already_done(db: Session, reminder: Reminder, tz_name: str) -> bool:
    from app.nutrition.models import Meal
    from app.progress.models import ProgressPhoto, WeightEntry

    tz = zone(tz_name)
    now = utcnow()
    today = local_now(tz).date()
    user = reminder.user_id
    if reminder.kind == "meal":
        recent = select(func.count(Meal.id)).where(
            Meal.user_id == user, Meal.created_at > now - timedelta(hours=3)
        )
        return db.scalar(recent) > 0
    if reminder.kind == "weight":
        weighed = select(func.count(WeightEntry.id)).where(
            WeightEntry.user_id == user, WeightEntry.measured_on == today
        )
        return db.scalar(weighed) > 0
    if reminder.kind == "photo":
        recent = select(func.count(ProgressPhoto.id)).where(
            ProgressPhoto.user_id == user, ProgressPhoto.taken_on > today - timedelta(days=6)
        )
        return db.scalar(recent) > 0
    return False


def send_due(db: Session) -> int:
    """Queues every reminder whose time has come and moves it to its next time."""
    from app.users.models import User

    now = utcnow()
    due = db.scalars(
        select(Reminder).where(Reminder.enabled.is_(True), Reminder.next_run_at <= now)
    ).all()
    sent = 0
    for reminder in due:
        user = db.get(User, reminder.user_id)
        tz_name = user.profile.timezone
        fresh = now - reminder.next_run_at < STALE
        if fresh and user.can_enter and user.telegram_id:
            if reminder.smart_skip and _already_done(db, reminder, tz_name):
                log.info("reminder %s skipped: already done", reminder.id)
            else:
                buttons = [[{"text": "🔕 Больше не напоминать", "data": f"r:off:{reminder.id}"}]]
                outbox.push(db, user, text(reminder), buttons)
                reminder.last_sent_at = now
                sent += 1
        reminder.next_run_at = next_run(reminder, tz_name, after=now)
    db.commit()
    return sent
