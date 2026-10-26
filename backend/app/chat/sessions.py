"""Sessions in the bot.

The assistant only hears what is said inside a session. A session starts with the
"New session" button (or /new, or a button that needs the assistant), sees all of its
messages and photos, and ends with "End" or after a quiet spell. Outside a session the
bot still records weights, measurements and progress photos by itself."""

from datetime import datetime, timedelta
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AiJob
from app.chat import outbox, views
from app.chat.models import ChatMessage, ChatSession
from app.chat.outbox import view
from app.config import get_settings
from app.core.timeutil import zone
from app.database import utcnow
from app.notes import service as notes
from app.users.models import User

NEW = "🟢 Новая сессия"
END = "⏹ Завершить сессию"
TODAY = "📊 Сегодня"
WEIGHT = "⚖️ Вес"
MEASURE = "📏 Замеры"
PROGRESS = "📸 Прогресс"
REVIEW = "🧾 Разбор"
MORE = "⚙️ Еще"
NOTE = "📝 Заметка"
KEYS = {NEW, END, TODAY, WEIGHT, MEASURE, PROGRESS, REVIEW, MORE, NOTE}
# Raise when the keyboard changes: everyone gets it again with a short note.
KEYBOARD_VERSION = 4
# The first few sessions explain themselves; later ones just say what happened.
INTRO_SESSIONS = 3


def keyboard(active: bool) -> list[list[str]]:
    return [
        [END if active else NEW, TODAY],
        [WEIGHT, MEASURE, PROGRESS],
        [NOTE, REVIEW, MORE],
    ]


def keyboard_view(text: str, active: bool, **extra) -> dict:
    """A message that puts the keyboard for this state under the input field: its hint
    says whether the assistant is listening."""
    return {
        **view(text, keyboard=keyboard(active)),
        "placeholder": "Сообщение ассистенту…"
        if active
        else "Нажмите «Новая сессия», чтобы писать ассистенту",
        "styles": {NEW: "success"},
        **extra,
    }


def intro(db: Session, user: User) -> bool:
    count = db.scalar(select(func.count(ChatSession.id)).where(ChatSession.user_id == user.id))
    return count <= INTRO_SESSIONS


def idle_limit() -> timedelta:
    return timedelta(minutes=get_settings().session_idle_minutes)


def busy(db: Session, user_id: int) -> bool:
    """The assistant is still working on something for this person."""
    jobs = select(func.count(AiJob.id)).where(
        AiJob.user_id == user_id, AiJob.status.in_(["queued", "running"])
    )
    return db.scalar(jobs) > 0


def _open(db: Session, user_id: int) -> ChatSession | None:
    return db.scalar(
        select(ChatSession)
        .where(ChatSession.user_id == user_id, ChatSession.ended_at.is_(None))
        .order_by(ChatSession.id.desc())
    )


def current(db: Session, user: User) -> ChatSession | None:
    """The open session; one left open past its quiet limit (the server was down) ends now."""
    session = _open(db, user.id)
    if session and _quiet(session, utcnow()) and not busy(db, user.id):
        finish(db, user, session, "idle", notify=True)
        return None
    return session


def _quiet(session: ChatSession, now: datetime) -> bool:
    return session.last_activity_at < now - idle_limit()


def start(db: Session, user: User) -> tuple[ChatSession, str | None]:
    """Opens a session; the one still open is closed first. -> (session, its summary)."""
    previous = _open(db, user.id)
    summary = finish(db, user, previous, "new") if previous else None
    session = ChatSession(user_id=user.id)
    db.add(session)
    db.flush()
    return session, summary


def ensure(db: Session, user: User) -> tuple[ChatSession, bool]:
    """The open session, or a new one. -> (session, whether it was just started)."""
    session = current(db, user)
    if session:
        return session, False
    return start(db, user)[0], True


def touch(session: ChatSession):
    session.last_activity_at = utcnow()


def finish(db: Session, user: User, session: ChatSession, reason: str, notify: bool = False) -> str:
    """Ends the session. -> what was recorded during it (for the closing message)."""
    session.ended_at = utcnow()
    session.end_reason = reason
    db.flush()
    text = summary(db, user, session)
    if notify:
        outbox.push(db, user, **ended_view(db, user, text, reason))
    return text


def plural(number: int, forms: tuple[str, str, str]) -> str:
    n = abs(number) % 100
    if 10 < n < 20:
        return forms[2]
    return forms[0] if n % 10 == 1 else forms[1] if 1 < n % 10 < 5 else forms[2]


def summary(db: Session, user: User, session: ChatSession) -> str:
    from app.nutrition.models import Meal, Product
    from app.progress.models import MEASUREMENTS, Measurement, ProgressPhoto, WeightEntry

    def made(model):
        return db.scalars(
            select(model).where(
                model.user_id == user.id,
                model.created_at >= session.started_at,
                model.created_at <= (session.ended_at or utcnow()),
            )
        ).all()

    lines = []
    meals = made(Meal)
    edited = db.scalar(
        select(func.count(Meal.id)).where(
            Meal.user_id == user.id,
            Meal.created_at < session.started_at,
            Meal.updated_at >= session.started_at,
        )
    )
    if meals:
        kcal = round(sum(meal.kcal for meal in meals))
        drafts = sum(meal.status == "draft" for meal in meals)
        line = (
            f"🍽 {len(meals)} {plural(len(meals), ('прием', 'приема', 'приемов'))} пищи, {kcal} ккал"
        )
        if drafts:
            line += f" (черновиков: {drafts})"
        lines.append(line)
    if edited:
        lines.append(f"✏️ Исправлено {edited} {plural(edited, ('запись', 'записи', 'записей'))}")
    weights = made(WeightEntry)
    if weights:
        lines.append(f"⚖️ Вес {views.n(weights[-1].weight_kg, 1)} кг")
    measurements = made(Measurement)
    if measurements:
        names = dict.fromkeys(MEASUREMENTS[m.kind][0].lower() for m in measurements)
        lines.append("📏 Замеры: " + ", ".join(names))
    photos = made(ProgressPhoto)
    if photos:
        lines.append(f"📸 Фото прогресса: {len(photos)}")
    products = made(Product)
    if products:
        lines.append("🏷 Продукты: " + ", ".join(escape(p.name) for p in products[:5]))
    if not lines:
        asked = db.scalar(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.session_id == session.id, ChatMessage.role == "user"
            )
        )
        return "💬 Только поговорили" if asked else "Ничего не записали"
    return "\n".join(lines)


def quiet_time() -> str:
    """How long a session waits: "час", "2 часа", "90 минут"."""
    minutes = get_settings().session_idle_minutes
    if minutes % 60:
        return f"{minutes} минут"
    hours = minutes // 60
    return "час" if hours == 1 else f"{hours} часа"


def started_view(db: Session, user: User, previous: str | None = None) -> dict:
    quiet = quiet_time()
    head = f"⏹ Прошлая сессия закрыта\n{previous}\n\n" if previous else ""
    if intro(db, user):
        body = (
            "🟢 <b>Сессия началась</b>\n"
            "Пишите и присылайте фото, можно несколькими сообщениями подряд: ассистент видит "
            "всё, что пришло в этой сессии.\n"
            f"<i>Закроется сама через {quiet} тишины.</i>"
        )
    else:
        body = f"🟢 <b>Сессия началась</b>\n<i>Закроется через {quiet} тишины</i>"
    # Food weighed in advance whose meal has come: the session is where it gets logged.
    tz = zone(user.profile.timezone)
    due = [note for note in notes.active(db, user.id) if notes.is_due(note)]
    if due:
        body += "\n\n" + "\n".join(views.note_line(note, tz) for note in due)
        body += "\n<i>Учесть: «по заметке» или фото еды.</i>"
    return keyboard_view(head + body, True)


def ended_view(db: Session, user: User, text: str, reason: str) -> dict:
    title = (
        f"⚪️ <b>Сессия закрыта</b>: {quiet_time()} тишины"
        if reason == "idle"
        else "⏹ <b>Сессия закрыта</b>"
    )
    tail = (
        "\n\n<i>Без сессии ассистент ничего не получает. Вес, замеры и фото прогресса "
        "я запишу и так.</i>"
        if intro(db, user)
        else ""
    )
    return keyboard_view(f"{title}\n{text}{tail}", False)


def close_idle(db: Session) -> int:
    """Ends the sessions that have been quiet too long (the maintenance loop calls this)."""
    now = utcnow()
    closed = 0
    for session in db.scalars(
        select(ChatSession).where(
            ChatSession.ended_at.is_(None), ChatSession.last_activity_at < now - idle_limit()
        )
    ).all():
        if busy(db, session.user_id):
            continue
        user = db.get(User, session.user_id)
        finish(db, user, session, "idle", notify=True)
        closed += 1
    db.commit()
    return closed
