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
from app.users import photo_lock
from app.users import service as users
from app.users.models import User

# /progress applies to the next photo only, and only for a while.
PROGRESS_MODE = timedelta(minutes=10)
PROGRESS_WORDS = re.compile(r"^\s*(прогресс|фото тела|фото прогресса|моя форма)\b", re.I)
WEIGHT = re.compile(
    r"^\s*(?P<word>вес|взвесил(?:ся|ась)?|weight)?\s*[:=-]?\s*"
    r"(?P<value>\d{2,3}(?:[.,]\d{1,2})?)\s*(?P<unit>кг|kg)?\.?\s*$",
    re.IGNORECASE,
)
HELP = (
    "<b>Как пользоваться</b>\n\n"
    "🍽 <b>Еда.</b> Пришлите фото тарелки или напишите, что съели: "
    "<i>«овсянка 60 г на молоке и банан»</i>. Я посчитаю КБЖУ и покажу черновик — "
    "нажмите «Сохранить» или напишите, что поправить: <i>«риса было 200 г»</i>.\n\n"
    "🏷 <b>Свои продукты.</b> Пришлите фото этикетки с подписью <i>«запомни мое молоко»</i> — "
    "сохраню КБЖУ и фото состава, потом <i>«стакан моего молока»</i> посчитаю точно.\n\n"
    "⚖️ <b>Вес и замеры.</b> Просто числом: <i>«вес 82.4»</i>, <i>«талия 80»</i>.\n\n"
    "📸 <b>Фото тела.</b> Подпишите фото словом «прогресс» или нажмите /progress перед "
    "отправкой. Остальные фото я считаю едой.\n\n"
    "💬 <b>Вопросы и разбор.</b> <i>«сколько белка за неделю?»</i>, <i>«что съесть на "
    "ужин?»</i>. /review — разбор рациона за день, неделю или месяц.\n\n"
    "/today — итоги дня · /new — новый разговор"
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
        if payload.startswith("login_"):
            users.refuse_login(db, payload[6:])
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


def link(db: Session, info: dict, code: str | None) -> dict:
    """/link <key>: the key comes from the site (Profile → Account → Link Telegram)."""
    if not code or not code.strip():
        return view(
            "Отправьте /link и ключ с сайта: Профиль → Аккаунт → «Привязать Telegram». "
            "Пароль отправлять не нужно."
        )
    try:
        text = users.link_telegram(db, code, info)
    except DomainError as error:
        return view(escape(error.message))
    return view(f"{text}\n\n{HELP}", site_row())


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
        "📸 Пришлите следующим сообщением фото тела (можно несколько сразу) — сохраню в "
        "альбом прогресса. Подпись станет комментарием. Эти фото не уходят в AI.",
        [[views.button("✖️ Отмена", "p:x")]],
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
    armed = state.mode == "progress" and bool(state.mode_until and state.mode_until > utcnow())
    # /progress covers the next message only: photos in it are body photos, anything else
    # means the person moved on.
    state.mode = None

    # Body photos: /progress right before, or the caption says so; they never leave the
    # server. Every other photo is treated as food by the assistant.
    if saved and (armed or PROGRESS_WORDS.match(text)):
        note = PROGRESS_WORDS.sub("", text).strip(" ,.:-—") or None
        created = [
            [
                "progress_photo",
                progress.make_progress_photo(db, user, item, pose=pose, note=note).id,
            ]
            for item, pose in zip(saved, progress.poses_for(len(saved)), strict=True)
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


def press(db: Session, user: User, data: str, message_id: int | None = None) -> dict:
    """-> {"view": message replacement or None, "toast": short note, "message": new message,
    "job_id": a started assistant job}"""
    parts = data.split(":")
    try:
        return _press(db, user, parts, message_id)
    except DomainError as error:
        return {"view": None, "toast": error.message, "message": None, "job_id": None}
    except (ValueError, IndexError):
        return {"view": None, "toast": "Кнопка устарела", "message": None, "job_id": None}


# Reviews of the recent days

REVIEW_PERIODS = {1: "сегодня", 7: "неделю", 14: "две недели", 30: "месяц"}


def review_menu() -> dict:
    labels = {1: "Сегодня", 7: "Неделя", 14: "2 недели", 30: "Месяц"}
    return view(
        "📊 <b>Разбор рациона</b>\n\nЗа какой период? Посмотрю, что получается хорошо и что "
        "можно улучшить.",
        [[views.button(labels[days], f"rv:{days}") for days in REVIEW_PERIODS]],
    )


def start_review(db: Session, user: User, days: int, status_message_id: int | None = None) -> AiJob:
    """Queues the assistant's review of the last `days` days (from a button or a reminder)."""
    if days not in REVIEW_PERIODS:
        raise DomainError("Такого периода нет")
    if get_settings().ai_runner == "off":
        raise DomainError(ERRORS["off"])
    message = ChatMessage(
        user_id=user.id, role="user", text=f"Разбор рациона за {REVIEW_PERIODS[days]}"
    )
    db.add(message)
    db.flush()
    job = AiJob(
        user_id=user.id,
        message_id=message.id,
        kind="review",
        days=days,
        status_message_id=status_message_id,
    )
    db.add(job)
    db.flush()
    return job


def _press(db: Session, user: User, parts: list[str], message_id: int | None) -> dict:
    head = parts[0]
    result = {"view": None, "toast": None, "message": None, "job_id": None}
    if head == "pin":
        if parts[1] == "reset" and photo_lock.confirm_reset(user.profile):
            text = "🔓 Код для фото прогресса сброшен. Новый можно задать в профиле на сайте."
        elif parts[1] == "reset":
            text = "Запрос устарел. Попросите сброс на сайте еще раз."
        else:
            user.profile.photo_pin_reset_at = None
            text = "Код оставили прежним."
        db.commit()
        result["view"] = view(text)
        return result
    if head == "rv":
        days = int(parts[1])
        job = start_review(db, user, days, message_id)
        db.commit()
        result["job_id"] = job.id
        result["view"] = view(f"⏳ Разбираю рацион за {REVIEW_PERIODS[days]}…")
        return result
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

    if head == "p" and parts[1] == "x":
        state_of(db, user).mode = None
        db.commit()
        result["view"] = view("Хорошо, следующее фото посчитаю едой.")
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
