"""Weigh notes: grams written down while weighing, waiting for the meal they belong to.

A note for "soon" burns after three hours. A note for a meal belongs to the next one of
that kind: weighed in the evening for lunch, it is tomorrow's lunch; weighed in the morning
for lunch, today's. It shows up an hour before the meal's hours, waits two hours after
them for a late meal, and then burns. Logging the meal with it marks it used.
"""

from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, NotFound
from app.core.timeutil import from_local, local_now, to_local, zone
from app.database import utcnow
from app.notes.models import WeighNote
from app.users.models import User

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
NAMES = {"breakfast": "завтрак", "lunch": "обед", "dinner": "ужин", "snack": "перекус"}
# Local hours of each meal, as the diary guesses meal types.
WINDOWS = {"breakfast": (5, 11), "lunch": (11, 16), "dinner": (16, 23)}
SOON = timedelta(hours=3)
SNACK = timedelta(hours=12)
LEAD = timedelta(hours=1)
GRACE = timedelta(hours=2)
MAX_ACTIVE = 30


def window(meal_type: str | None, now: datetime) -> tuple[datetime, datetime]:
    """(shows up from, burns at) in local time for a note written at `now` (aware)."""
    if meal_type is None:
        return now, now + SOON
    if meal_type == "snack":
        return now, now + SNACK
    start_hour, end_hour = WINDOWS[meal_type]
    day = now.date()
    if now >= datetime.combine(day, time(end_hour), now.tzinfo):
        day += timedelta(days=1)
    start = datetime.combine(day, time(start_hour), now.tzinfo)
    end = datetime.combine(day, time(end_hour), now.tzinfo)
    return max(now, start - LEAD), end + GRACE


def place(note: WeighNote, meal_type: str | None, user: User) -> None:
    if meal_type is not None and meal_type not in MEAL_TYPES:
        raise DomainError("Нет такого приема пищи")
    tz = zone(user.profile.timezone)
    due, burns = window(meal_type, local_now(tz))
    note.meal_type = meal_type
    note.due_from = from_local(due, tz)
    note.expires_at = from_local(burns, tz)


def clean(text: str) -> str:
    lines = [" ".join(line.split()) for line in (text or "").strip().splitlines()]
    text = "\n".join(line for line in lines if line)[:1000]
    if not text:
        raise DomainError("Пустая заметка: напишите, что и сколько взвесили")
    return text


def active(db: Session, user_id: int) -> list[WeighNote]:
    return list(
        db.scalars(
            select(WeighNote)
            .where(
                WeighNote.user_id == user_id,
                WeighNote.status == "active",
                WeighNote.expires_at > utcnow(),
            )
            .order_by(WeighNote.due_from, WeighNote.id)
        )
    )


def create(db: Session, user: User, text: str, meal_type: str | None, source: str) -> WeighNote:
    if len(active(db, user.id)) >= MAX_ACTIVE:
        raise DomainError(f"Уже {MAX_ACTIVE} заметок ждут. Учтите или удалите старые")
    note = WeighNote(user_id=user.id, text=clean(text), source=source)
    place(note, meal_type, user)
    db.add(note)
    db.flush()
    return note


def owned(db: Session, note_id: int, user_id: int) -> WeighNote:
    note = db.get(WeighNote, note_id)
    if not note or note.user_id != user_id or note.status == "deleted":
        raise NotFound("Заметка не найдена")
    return note


def usable(db: Session, note_id: int, user_id: int) -> WeighNote:
    note = owned(db, note_id, user_id)
    if note.status != "active" or note.expires_at <= utcnow():
        raise DomainError("Заметка уже учтена или сгорела")
    return note


def use(note: WeighNote, meal_id: int | None) -> None:
    note.status = "used"
    note.meal_id = meal_id
    note.used_at = utcnow()


def is_due(note: WeighNote) -> bool:
    return note.due_from <= utcnow()


def label(note: WeighNote, tz) -> str:
    """ "на обед, сегодня", "на ужин, завтра", "на 3 часа, до 14:30"."""
    burns = to_local(note.expires_at, tz)
    if note.meal_type is None:
        return f"на ближайшие часы, до {burns:%H:%M}"
    if note.meal_type == "snack":
        return f"на перекус, до {burns:%H:%M}"
    day = to_local(note.expires_at - GRACE, tz).date()
    today = local_now(tz).date()
    when = "сегодня" if day == today else "завтра" if day == today + timedelta(days=1) else ""
    return f"на {NAMES[note.meal_type]}" + (f", {when}" if when else "")


def out(note: WeighNote, user: User) -> dict:
    tz = zone(user.profile.timezone)
    return {
        "id": note.id,
        "text": note.text,
        "meal_type": note.meal_type,
        "due": is_due(note),
        "label": label(note, tz),
        "due_from": to_local(note.due_from, tz).isoformat(timespec="minutes"),
        "expires_at": to_local(note.expires_at, tz).isoformat(timespec="minutes"),
        "source": note.source,
    }
