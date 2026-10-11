"""What happens with a message, a button press or a command from the bot."""

import re
from datetime import timedelta
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.actions import execute_pending
from app.ai.jobs import ERRORS
from app.ai.models import AiJob
from app.chat import views
from app.chat.models import ChatMessage, ChatState, PendingAction
from app.chat.outbox import view
from app.config import get_settings
from app.core.exceptions import DomainError
from app.core.timeutil import local_today, zone
from app.database import utcnow
from app.media import service as media
from app.media.storage import Storage
from app.nutrition import service as nutrition
from app.nutrition.models import Meal
from app.progress import service as progress
from app.reminders import service as reminders
from app.users import service as users
from app.users.models import User

PROGRESS_MODE = timedelta(minutes=15)
PROGRESS_WORDS = re.compile(r"^\s*(прогресс|фото тела|фото прогресса|моя форма)\b", re.I)
WEIGHT = re.compile(
    r"^\s*(?P<word>вес|взвесил(?:ся|ась)?|weight)?\s*[:=-]?\s*"
    r"(?P<value>\d{2,3}(?:[.,]\d{1,2})?)\s*(?P<unit>кг|kg)?\.?\s*$",
    re.IGNORECASE,
)
HELP = (
    "Я помогаю вести дневник питания и следить за прогрессом.\n\n"
    "• Пришлите <b>фото еды</b> — оценю состав, вес и КБЖУ.\n"
    "• Или опишите словами: <i>«овсянка 60 г на молоке и банан»</i>.\n"
    "• Вес: <i>«вес 82.4»</i>, замеры: <i>«талия 80, бедра 98»</i>.\n"
    "• Фото тела: подпишите «прогресс» или нажмите /progress.\n"
    "• Исправления словами: <i>«в обеде риса было 200 г»</i>, <i>«удали вчерашний ужин»</i>.\n"
    "• Вопросы: <i>«сколько белка я съел за неделю?»</i>, <i>«что съесть на ужин?»</i>\n"
    "• Напоминания: <i>«напоминай взвешиваться в 8 утра»</i>.\n\n"
    "/today — итоги дня, /new — новый разговор, /app — дневник на сайте."
)


def state_of(db: Session, user: User) -> ChatState:
    state = db.get(ChatState, user.id)
    if not state:
        state = ChatState(user_id=user.id)
        db.add(state)
        db.flush()
    return state


def site_row(text: str = "🌐 Открыть дневник", path: str = "/") -> list:
    button = views.site_button(text, path)
    return [[button]] if button else []


# /start and commands


def start(db: Session, info: dict, payload: str | None) -> dict:
    payload = (payload or "").strip()
    invite = payload[4:] if payload.startswith("inv_") else None
    try:
        user, created = users.ensure_user(db, info, invite)
    except DomainError as error:
        return view(escape(error.message))
    if payload.startswith("login_"):
        request = users.pending_login(db, payload[6:])
        if not request:
            return view("Ссылка для входа устарела. Обновите страницу входа и попробуйте снова.")
        device = escape(request.user_agent or "неизвестное устройство")[:120]
        return view(
            "🔐 <b>Войти на сайт дневника?</b>\n\n"
            f"Устройство: {device}\n\n"
            "Подтверждайте, только если вход начали вы сами.",
            [
                [
                    views.button("✅ Да, это я", f"l:y:{request.code}"),
                    views.button("✖️ Нет", f"l:n:{request.code}"),
                ]
            ],
        )
    greeting = (
        f"Привет, {escape(user.first_name or 'друг')}! 👋\n\n"
        if created
        else "С возвращением! 👋\n\n"
    )
    return view(greeting + HELP, site_row())


def today(db: Session, user: User) -> dict:
    summary = nutrition.day_summary(db, user)
    weight = progress.latest_weight(db, user.id)
    change = progress.weight_change(db, user, 7)
    return views.today_view(summary, summary["day"], weight, change)


def new_conversation(db: Session, user: User) -> dict:
    state = state_of(db, user)
    state.context_from = utcnow()
    state.focus_meal_id = None
    db.commit()
    return view("🆕 Начали новый разговор. Записи и память на месте.")


def progress_mode(db: Session, user: User) -> dict:
    state = state_of(db, user)
    state.mode = "progress"
    state.mode_until = utcnow() + PROGRESS_MODE
    db.commit()
    return view(
        "📸 Присылайте фото прогресса — сохраню их в альбом. Режим включен на 15 минут, "
        "подпись к фото станет комментарием. Эти фото не отправляются в AI."
    )


def app_link() -> dict:
    if not get_settings().app_url:
        return view("Адрес сайта пока не настроен.")
    return view("Дневник, графики и фото — на сайте:", site_row())


# Messages


def _with_undo(db: Session, user: User, text: str, created: list) -> dict:
    action = PendingAction(
        user_id=user.id,
        kind="undo",
        payload={"items": created, "text": text, "buttons": []},
        summary="Отменить записанное",
        expires_at=utcnow() + timedelta(hours=24),
    )
    db.add(action)
    db.flush()
    return view(text, [[views.button("↩️ Отменить", f"u:{action.id}")]])


def _answer(db: Session, user: User, result: dict) -> dict:
    db.add(ChatMessage(user_id=user.id, role="assistant", text=result["text"]))
    db.commit()
    return {"view": result, "job_id": None}


def parse_weight(text: str) -> float | None:
    match = WEIGHT.match(text or "")
    if not match:
        return None
    value = float(match["value"].replace(",", "."))
    explicit = match["word"] or match["unit"] or "." in match["value"] or "," in match["value"]
    return value if explicit and 25 <= value <= 300 else None


def receive(
    db: Session,
    storage: Storage,
    user: User,
    text: str,
    photos: list[bytes],
    telegram_message_id: int | None,
    status_message_id: int | None,
) -> dict:
    """Saves the message; answers at once when no AI is needed, else queues a job."""
    text = (text or "").strip()[:4000]
    user.last_seen_at = utcnow()
    message = ChatMessage(
        user_id=user.id,
        role="user",
        text=text,
        photos=len(photos),
        telegram_message_id=telegram_message_id,
    )
    db.add(message)
    db.flush()
    saved = [
        media.save_photo(db, storage, user.id, data, "chat", message_id=message.id)
        for data in photos
    ]
    state = state_of(db, user)
    if state.mode == "progress" and (not state.mode_until or state.mode_until < utcnow()):
        state.mode = None

    # Body photos: explicit mode or caption; they never leave the server.
    if saved and (state.mode == "progress" or PROGRESS_WORDS.match(text)):
        note = PROGRESS_WORDS.sub("", text).strip(" ,.:-—") or None
        created = [
            ["progress_photo", progress.make_progress_photo(db, user, item, note=note).id]
            for item in saved
        ]
        count = f" ({len(saved)} шт.)" if len(saved) > 1 else ""
        return _answer(
            db, user, _with_undo(db, user, f"📸 Сохранил фото прогресса{count}", created)
        )

    weight = parse_weight(text) if not saved else None
    if weight:
        entry = progress.add_weight(db, user, weight, source="bot")
        db.flush()
        change = progress.weight_change(db, user, 7)
        tail = f" ({'+' if change > 0 else ''}{views.n(change, 1)} за неделю)" if change else ""
        reply = f"⚖️ Записал вес: {views.n(entry.weight_kg, 1)} кг{tail}"
        return _answer(db, user, _with_undo(db, user, reply, [["weight", entry.id]]))

    if get_settings().ai_runner == "off":
        return _answer(db, user, view(f"😕 {ERRORS['off']}"))

    job = AiJob(user_id=user.id, message_id=message.id, status_message_id=status_message_id)
    db.add(job)
    db.commit()
    return {"view": None, "job_id": job.id}


# Buttons


def _meal(db: Session, user: User, meal_id: str) -> Meal:
    meal = db.get(Meal, int(meal_id))
    if not meal or meal.user_id != user.id:
        raise DomainError("Запись уже удалена")
    return meal


def _meal_view(db: Session, user: User, meal: Meal, deleting: bool = False) -> dict:
    today_ = local_today(zone(user.profile.timezone))
    total = nutrition.totals(nutrition.list_meals(db, user.id, today_, today_))
    return views.meal_view(
        meal, user.profile.timezone, total, user.profile.kcal_target, deleting=deleting
    )


def press(db: Session, user: User, data: str) -> dict:
    """-> {"view": message replacement or None, "toast": short note, "message": new message}"""
    parts = data.split(":")
    try:
        return _press(db, user, parts)
    except DomainError as error:
        return {"view": None, "toast": error.message, "message": None}
    except (ValueError, IndexError):
        return {"view": None, "toast": "Кнопка устарела", "message": None}


def _press(db: Session, user: User, parts: list[str]) -> dict:
    head = parts[0]
    result = {"view": None, "toast": None, "message": None}
    if head == "m":
        action, meal = parts[1], _meal(db, user, parts[2])
        if action == "ok":
            nutrition.confirm(meal)
            db.commit()
            result["toast"] = "Сохранено"
        elif action == "t":
            meal.meal_type = views.TYPE_CODES[parts[3]]
            db.commit()
        elif action == "e":
            state = state_of(db, user)
            state.focus_meal_id = meal.id
            db.commit()
            result["message"] = view(
                f"✏️ Что исправить в «{escape(meal.title)}»? Напишите, например: "
                "<i>«риса было 200 г»</i>, <i>«без соуса»</i> или <i>«это был ужин»</i>."
            )
            return result
        elif action == "x":
            title = meal.title
            nutrition.delete(db, meal)
            db.commit()
            result["view"] = view(f"🗑 Черновик удален: «{escape(title)}»")
            return result
        elif action == "d":
            result["view"] = _meal_view(db, user, meal, deleting=True)
            return result
        elif action == "dd":
            title = meal.title
            nutrition.delete(db, meal)
            db.commit()
            result["view"] = view(f"🗑 Удалено: «{escape(title)}»")
            return result
        result["view"] = _meal_view(db, user, meal)
        return result

    if head in ("a", "u"):
        action_id = int(parts[2] if head == "a" else parts[1])
        action = db.get(PendingAction, action_id)
        if not action or action.user_id != user.id:
            raise DomainError("Кнопка устарела")
        if action.status != "pending" or action.expires_at < utcnow():
            raise DomainError("Уже выполнено или устарело")
        if head == "a" and parts[1] == "n":
            action.status = "cancelled"
            db.commit()
            result["view"] = view(f"{escape(action.summary)}\n\n✖️ Хорошо, ничего не меняю.")
            return result
        done = execute_pending(db, user, action)
        action.status = "done"
        db.commit()
        if head == "u":
            text = action.payload.get("text", "")
            result["view"] = view(f"{text}\n\n{done}", action.payload.get("buttons") or [])
        else:
            result["view"] = view(f"{escape(action.summary)}\n\n{done}")
        return result

    if head == "l":
        approve = parts[1] == "y"
        if not users.answer_login(db, parts[2], user, approve):
            raise DomainError("Запрос на вход устарел")
        result["view"] = view(
            "✅ Вход подтвержден. Вернитесь в браузер." if approve else "✖️ Вход отклонен."
        )
        return result

    if head == "r" and parts[1] == "off":
        reminder = reminders.owned(db, int(parts[2]), user.id)
        reminder.enabled = False
        reminder.next_run_at = None
        db.commit()
        result["view"] = view(
            f"🔕 Выключено: {escape(reminders.describe(reminder))}. "
            "Включить снова можно в профиле на сайте или попросить меня."
        )
        return result
    raise ValueError(head)


def pending_jobs(db: Session, user: User) -> int:
    return len(
        db.scalars(
            select(AiJob.id).where(
                AiJob.user_id == user.id, AiJob.status.in_(["queued", "running"])
            )
        ).all()
    )
