"""What happens with a message, a button press or a command from the bot."""

import re
from datetime import timedelta
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.actions import execute_pending
from app.ai.jobs import ERRORS
from app.ai.models import AiJob
from app.chat import outbox, sessions, views
from app.chat.models import ChatMessage, ChatState, PendingAction
from app.chat.outbox import view
from app.config import get_settings
from app.core.exceptions import DomainError
from app.core.timeutil import local_today, zone
from app.database import utcnow
from app.media import service as media
from app.media.models import Media
from app.media.storage import Storage
from app.notes import service as notes
from app.nutrition import service as nutrition
from app.nutrition.models import Meal
from app.progress import daily
from app.progress import service as progress
from app.progress.models import MEASUREMENTS
from app.reminders import service as reminders
from app.users import photo_lock
from app.users import service as users
from app.users.models import User

# /progress applies to the next photo only, and only for a while.
PROGRESS_MODE = timedelta(minutes=10)
AWAITING = timedelta(minutes=10)
PROGRESS_WORDS = re.compile(r"^\s*(прогресс|фото тела|фото прогресса|моя форма)\b", re.I)
# "заметка на обед: 130 грудка, 150 рис" — grams for later, saved without the assistant.
NOTE_TEXT = re.compile(
    r"^\s*(?:📝\s*)?заметк[аиу]\b\s*"
    r"(?:(?:на|к|для)\s+(?P<meal>завтрак|обед|ужин|перекус)\w*)?\s*[:\-—,.]?\s*(?P<text>.+)$",
    re.I | re.S,
)
NOTE_MEALS = {"завтрак": "breakfast", "обед": "lunch", "ужин": "dinner", "перекус": "snack"}
WEIGHT = re.compile(
    r"^\s*(?P<word>вес|взвесил(?:ся|ась)?|weight)?\s*[:=-]?\s*"
    r"(?P<value>\d{2,3}(?:[.,]\d{1,2})?)\s*(?P<unit>кг|kg)?\.?\s*$",
    re.IGNORECASE,
)
# "талия 82, бедра 98,5": measurement names as people write them.
MEASURE_NAMES = {
    "waist": r"тали[яиюей]|waist",
    "hips": r"б[её]дра|б[её]дер|hips",
    "chest": r"груд[ьи]|грудь|chest",
    "neck": r"ше[яиюей]|neck",
    "arm": r"бицепс\w*|рук[аиу]|arm",
    "thigh": r"бедро|бедре|thigh",
    "calf": r"голен[ьи]|икр[аыу]|calf",
    "body_fat": r"(?:процент\s+)?жир\w*|body\s*fat",
}
MEASURE = re.compile(
    r"\b(?:" + "|".join(f"(?P<{kind}>{words})" for kind, words in MEASURE_NAMES.items()) + r")"
    r"\s*[:=-]?\s*(?P<value>\d{1,3}(?:[.,]\d{1,2})?)\s*(?:см|cm|%)?",
    re.IGNORECASE,
)
LEFTOVER = re.compile(r"^[\s,;.и+]*$", re.IGNORECASE)
HELP = (
    "<b>Как это работает</b>\n\n"
    "🟢 <b>Сессия</b> — разговор с ассистентом. Нажмите «Новая сессия» и пишите как в "
    "обычном чате: текст, фото, несколько сообщений подряд. Ассистент видит всё, что пришло "
    "в сессии, считает КБЖУ, отвечает на вопросы. Через {quiet} тишины сессия закроется "
    "сама.\n\n"
    "🍽 <b>Еда.</b> В сессии пришлите фото тарелки или напишите, что съели: "
    "<i>«овсянка 60 г на молоке и банан»</i>. Придет черновик: «Сохранить» или напишите, что "
    "поправить.\n\n"
    "Без сессии ассистент ничего не получает, а кнопки внизу работают всегда:\n"
    "⚖️ <b>Вес</b> и 📏 <b>Замеры</b> — запишу числа сразу\n"
    "📸 <b>Прогресс</b> — фото тела в альбом\n"
    "📊 <b>Сегодня</b> — итоги дня\n"
    "📝 <b>Заметка</b> — взвесили еду заранее: граммы подождут нужного приема пищи\n"
    "🧾 <b>Разбор</b> — ассистент разберет рацион (откроет сессию)\n\n"
    "Вес можно прислать и просто числом: <i>«82,4»</i>, замеры строкой: "
    "<i>«талия 82, бедра 98»</i>."
)


def help_text() -> str:
    return HELP.replace("{quiet}", sessions.quiet_time())


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


def _with_keyboard(db: Session, user: User, text: str) -> dict:
    state_of(db, user).keyboard_version = sessions.KEYBOARD_VERSION
    return sessions.keyboard_view(text, sessions.current(db, user) is not None)


def _announce(db: Session, user: User):
    """People who have not got the current keyboard get it once, with what changed."""
    state = state_of(db, user)
    if state.keyboard_version >= sessions.KEYBOARD_VERSION:
        return
    state.keyboard_version = sessions.KEYBOARD_VERSION
    outbox.push(
        db,
        user,
        **sessions.keyboard_view(
            "✨ <b>Бот обновился</b>\n"
            "• 📝 <b>Заметки</b>: взвесили еду заранее — нажмите «📝 Заметка» и пришлите "
            "граммы. Выберите, к какому приему: заметка всплывет к нему, а в сессии ассистент "
            "сам учтет эти граммы. Можно и одной строкой: <i>«заметка на обед: 130 грудка, "
            "150 рис»</i>\n"
            "• На сайте заметки — на главной и в «Записать»",
            sessions.current(db, user) is not None,
        ),
    )


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
    result = _with_keyboard(db, user, greeting + help_text())
    db.commit()
    return result


def help_view(db: Session, user: User) -> dict:
    result = _with_keyboard(db, user, help_text())
    db.commit()
    return result


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
    return sessions.keyboard_view(f"{text}\n\n{help_text()}", False)


def today(db: Session, user: User) -> dict:
    summary = nutrition.day_summary(db, user)
    weight = progress.latest_weight(db, user.id)
    change = progress.weight_change(db, user, 7)
    result = views.today_view(summary, summary["day"], weight, change)
    waiting = notes.active(db, user.id)
    if waiting:
        tz = zone(user.profile.timezone)
        lines = "\n".join(views.note_line(note, tz) for note in waiting)
        result["text"] += f"\n\n<b>Ждут учета</b>\n{lines}"
    return result


# Weigh notes


def ask_note(db: Session, user: User) -> dict:
    """The note key and /note without text: the next message becomes a note."""
    state = state_of(db, user)
    state.awaiting, state.awaiting_until = "note", utcnow() + AWAITING
    waiting = notes.active(db, user.id)
    db.commit()
    tz = zone(user.profile.timezone)
    listed = (
        "\n\n<b>Уже ждут</b>\n" + "\n".join(views.note_line(note, tz) for note in waiting)
        if waiting
        else ""
    )
    return view(
        "📝 Пришлите, что взвесили, по строке на продукт: <i>130 грудка, 150 рис басмати</i>. "
        "К какому приему — выберете кнопкой. Можно сразу: <i>«на обед: …»</i>." + listed,
        [[views.button("✖️ Отмена", "aw:x")]],
    )


def save_note(db: Session, user: User, text: str) -> dict:
    """A note from the bot; "на обед: …" in front picks the meal, else it is for soon."""
    match = NOTE_TEXT.match(text) or re.match(
        r"^\s*(?:(?:на|к|для)\s+(?P<meal>завтрак|обед|ужин|перекус)\w*)?\s*[:\-—,.]?\s*"
        r"(?P<text>.+)$",
        text,
        re.I | re.S,
    )
    meal = NOTE_MEALS.get((match["meal"] or "").lower()) if match else None
    note = notes.create(db, user, match["text"] if match else text, meal, "bot")
    db.commit()
    return views.note_view(note, user.profile.timezone, "Заметка сохранена")


def note_command(db: Session, user: User, text: str | None) -> dict:
    """/note [text]."""
    _announce(db, user)
    return save_note(db, user, text) if text and text.strip() else ask_note(db, user)


def new_session(db: Session, user: User) -> dict:
    """/new and the "New session" button."""
    if get_settings().ai_runner == "off":
        return view(f"😕 {ERRORS['off']}")
    _, previous = sessions.start(db, user)
    state = state_of(db, user)
    state.focus_meal_id = None
    state.keyboard_version = sessions.KEYBOARD_VERSION
    result = sessions.started_view(db, user, previous)
    db.commit()
    return result


def end_session(db: Session, user: User) -> dict:
    """/end and the "End session" button."""
    session = sessions.current(db, user)
    if not session:
        db.commit()
        return sessions.keyboard_view("Сессия уже закрыта.", False)
    text = sessions.finish(db, user, session, "user")
    state = state_of(db, user)
    state.focus_meal_id = None
    state.keyboard_version = sessions.KEYBOARD_VERSION
    result = sessions.ended_view(db, user, text, "user")
    db.commit()
    return result


def progress_mode(db: Session, user: User) -> dict:
    state = state_of(db, user)
    state.mode = "progress"
    state.mode_until = utcnow() + PROGRESS_MODE
    db.commit()
    return view(
        "📸 Пришлите следующим сообщением фото тела (можно несколько сразу: спереди, сзади, "
        "сбоку). Сохраню их одной записью в альбом прогресса, подпись станет заметкой. Эти "
        "фото не уходят ассистенту.",
        [[views.button("✖️ Отмена", "p:x")]],
    )


def app_link() -> dict:
    if not get_settings().app_url:
        return view("Адрес сайта пока не настроен.")
    return view("Дневник, графики и фото — на сайте:", site_row())


def ask_weight(db: Session, user: User) -> dict:
    state = state_of(db, user)
    state.awaiting, state.awaiting_until = "weight", utcnow() + AWAITING
    last = progress.latest_weight(db, user.id)
    db.commit()
    hint = (
        f"\nПоследний: {views.n(last.weight_kg, 1)} кг, {last.measured_on:%d.%m}." if last else ""
    )
    return view(
        f"⚖️ Пришлите вес числом, например <b>82,4</b>.{hint}",
        [[views.button("✖️ Отмена", "aw:x")]],
    )


def ask_measurements(db: Session, user: User) -> dict:
    state = state_of(db, user)
    state.awaiting, state.awaiting_until = "measure", utcnow() + AWAITING
    db.commit()
    names = ", ".join(name.lower() for name, _ in MEASUREMENTS.values())
    return view(
        "📏 Пришлите замеры одной строкой, можно только часть:\n"
        "<i>талия 82, бедра 98, грудь 101</i>\n\n"
        f"Знаю: {names}.",
        [[views.button("✖️ Отмена", "aw:x")]],
    )


def more_view() -> dict:
    rows = site_row("🌐 Открыть дневник") + site_row("⏰ Напоминания", "/profile?section=reminders")
    rows.append([views.button("❓ Как пользоваться", "h:help")])
    return view("⚙️ <b>Еще</b>", rows)


def keyboard_action(db: Session, user: User, label: str) -> dict:
    """A tap on the keyboard under the input field: never goes to the assistant."""
    if label == sessions.NEW:
        return new_session(db, user)
    if label == sessions.END:
        return end_session(db, user)
    if label == sessions.TODAY:
        return today(db, user)
    if label == sessions.WEIGHT:
        return ask_weight(db, user)
    if label == sessions.MEASURE:
        return ask_measurements(db, user)
    if label == sessions.PROGRESS:
        return progress_mode(db, user)
    if label == sessions.REVIEW:
        return review_menu()
    if label == sessions.NOTE:
        return ask_note(db, user)
    return more_view()


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


def _answer(db: Session, user: User, result: dict, session_id: int | None = None) -> dict:
    db.add(
        ChatMessage(user_id=user.id, role="assistant", text=result["text"], session_id=session_id)
    )
    db.commit()
    return {"view": result, "job_id": None}


def parse_weight(text: str, loose: bool = False) -> float | None:
    """ "вес 82.4", "82,4 кг"; a bare whole number only when the bot asked for the weight."""
    match = WEIGHT.match(text or "")
    if not match:
        return None
    value = float(match["value"].replace(",", "."))
    explicit = match["word"] or match["unit"] or "." in match["value"] or "," in match["value"]
    return value if (explicit or loose) and 25 <= value <= 300 else None


def parse_measurements(text: str) -> dict[str, float] | None:
    """ "талия 82, бедра 98" -> {"waist": 82, "hips": 98}; None unless that is all it says."""
    found: dict[str, float] = {}
    for match in MEASURE.finditer(text or ""):
        kind = next(name for name in MEASURE_NAMES if match[name])
        found[kind] = float(match["value"].replace(",", "."))
    if not found or not LEFTOVER.match(MEASURE.sub("", text)):
        return None
    return found


def _save_weight(db: Session, user: User, value: float, session_id: int | None) -> dict:
    entry, ask = daily.weight(db, user, value)
    if ask:
        return _answer(db, user, daily.replace_view(ask), session_id)
    change = progress.weight_change(db, user, 7)
    tail = f" ({'+' if change > 0 else ''}{views.n(change, 1)} за неделю)" if change else ""
    reply = f"⚖️ Записал вес: {views.n(entry.weight_kg, 1)} кг{tail}"
    return _answer(db, user, _with_undo(db, user, reply, [["weight", entry.id]]), session_id)


def _save_measurements(
    db: Session, user: User, values: dict[str, float], session_id: int | None
) -> dict:
    try:
        entries, ask = daily.measurements(db, user, values)
    except DomainError:
        return _answer(db, user, view("Не похоже на замеры: проверьте числа."), session_id)
    if not entries:
        return _answer(db, user, daily.replace_view(ask), session_id)
    saved = ", ".join(
        f"{MEASUREMENTS[e.kind][0].lower()} {views.n(e.value, 1)}"
        f"{'%' if e.kind == 'body_fat' else ' см'}"
        for e in entries
    )
    created = [["measurement", e.id] for e in entries]
    answer = _with_undo(db, user, f"📏 Записал: {saved}", created)
    if ask:
        # The new ones are saved; the ones already there wait for an answer.
        question = daily.replace_view(ask)
        answer = view(
            f"{answer['text']}\n\n{question['text']}", question["buttons"] + answer["buttons"]
        )
    return _answer(db, user, answer, session_id)


def _save_progress(db: Session, user: User, saved: list[Media], text: str, session_id) -> dict:
    note = PROGRESS_WORDS.sub("", text).strip(" ,.:-—") or None
    records, ask = daily.progress_photos(db, user, saved, note)
    if ask:
        return _answer(db, user, daily.replace_view(ask, add=True), session_id)
    created = [["progress_photo", record.id] for record in records]
    count = f" ({len(saved)} шт.)" if len(saved) > 1 else ""
    return _answer(
        db, user, _with_undo(db, user, f"📸 Сохранил фото прогресса{count}", created), session_id
    )


def queue_turn(db: Session, user: User, message: ChatMessage, status_message_id=None) -> AiJob:
    """The assistant answers the session's new messages together: a job waiting to start
    takes this one too and waits a little longer for more."""
    later = utcnow() + timedelta(seconds=get_settings().ai_debounce)
    waiting = db.scalar(
        select(AiJob).where(
            AiJob.user_id == user.id, AiJob.status == "queued", AiJob.kind == "turn"
        )
    )
    if waiting:
        waiting.message_id = message.id
        waiting.not_before = later
        return waiting
    job = AiJob(
        user_id=user.id,
        message_id=message.id,
        status_message_id=status_message_id,
        not_before=later,
    )
    db.add(job)
    db.flush()
    return job


def _outside_session(message: ChatMessage, photos: bool) -> dict:
    rows = [[views.button("🟢 Отправить ассистенту", f"s:go:{message.id}", "success")]]
    if photos:
        rows.append([views.button("📸 Это фото прогресса", f"s:pr:{message.id}")])
    return view(
        "💤 <b>Сессия не начата</b>, ассистент этого не видел. Отправить ему? Начнется сессия.",
        rows,
    )


def receive(
    db: Session,
    storage: Storage,
    user: User,
    text: str,
    photos: list[bytes],
    telegram_message_id: int | None,
    status_message_id: int | None,
) -> dict:
    """Keyboard taps, numbers the bot asked for, weights and measurements are handled
    here at once; everything else goes to the assistant only inside a session."""
    text = (text or "").strip()[:4000]
    user.last_seen_at = utcnow()
    if text in sessions.KEYS and not photos:
        return {"view": keyboard_action(db, user, text), "job_id": None}

    _announce(db, user)
    session = sessions.current(db, user)
    session_id = session.id if session else None
    message = ChatMessage(
        user_id=user.id,
        role="user",
        text=text,
        photos=len(photos),
        telegram_message_id=telegram_message_id,
        session_id=session_id,
    )
    db.add(message)
    db.flush()
    saved = [
        media.save_photo(db, storage, user.id, data, "chat", message_id=message.id)
        for data in photos
    ]
    state = state_of(db, user)
    now = utcnow()
    if session:
        sessions.touch(session)
    armed = state.mode == "progress" and bool(state.mode_until and state.mode_until > now)
    awaiting = state.awaiting if state.awaiting_until and state.awaiting_until > now else None
    # /progress and the number prompts cover the next message only.
    state.mode = None
    state.awaiting = None

    # What the bot answers by itself stays out of the session's conversation, so the
    # assistant never records it a second time.
    # Body photos: /progress right before, or the caption says so; they never leave the
    # server.
    if saved and (armed or PROGRESS_WORDS.match(text)):
        message.session_id = None
        return _save_progress(db, user, saved, text, None)
    # Grams for later never go to the assistant as a meal.
    if not saved and text and (awaiting == "note" or NOTE_TEXT.match(text)):
        message.session_id = None
        return {"view": save_note(db, user, text), "job_id": None}
    if not saved:
        weight = parse_weight(text, loose=awaiting == "weight")
        values = parse_measurements(text) if not weight or awaiting == "measure" else None
        if weight and awaiting != "measure":
            message.session_id = None
            return _save_weight(db, user, weight, None)
        if values:
            message.session_id = None
            return _save_measurements(db, user, values, None)
        # A miss with numbers is a typo; words mean the person moved on.
        if awaiting in ("weight", "measure") and re.search(r"\d", text):
            message.session_id = None
            state.awaiting, state.awaiting_until = awaiting, now + AWAITING
            hint = (
                "Не похоже на вес. Пришлите число, например 82,4."
                if awaiting == "weight"
                else "Не понял замеры. Пример: <i>талия 82, бедра 98</i>."
            )
            return _answer(db, user, view(hint))

    if not session:
        db.commit()
        return {"view": _outside_session(message, bool(saved)), "job_id": None}
    if get_settings().ai_runner == "off":
        return _answer(db, user, view(f"😕 {ERRORS['off']}"), session_id)
    job = queue_turn(db, user, message, status_message_id)
    db.commit()
    return {"view": None, "job_id": job.id}


# Buttons


def _meal(db: Session, user: User, meal_id: str) -> Meal:
    meal = db.get(Meal, int(meal_id))
    if not meal or meal.user_id != user.id:
        raise DomainError("Запись уже удалена")
    return meal


def _meal_view(
    db: Session, user: User, meal: Meal, deleting: bool = False, changes: list | None = None
) -> dict:
    today_ = local_today(zone(user.profile.timezone))
    total = nutrition.totals(nutrition.list_meals(db, user.id, today_, today_))
    return views.meal_view(
        meal,
        user.profile.timezone,
        total,
        nutrition.targets(user),
        deleting=deleting,
        changes=changes,
    )


def _note_answer(db: Session, user: User, text: str):
    """A button answer goes into the session's conversation: the assistant then knows
    that its proposal was taken or turned down."""
    session = sessions.current(db, user)
    if session:
        db.add(ChatMessage(user_id=user.id, role="assistant", text=text, session_id=session.id))


def press(db: Session, user: User, data: str, message_id: int | None = None) -> dict:
    """-> {"view": message replacement or None, "toast": short note, "message": new message,
    "job_id": a started assistant job}"""
    parts = data.split(":")
    _announce(db, user)
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
        "🧾 <b>Разбор рациона</b>\n\nЗа какой период? Посмотрю, что получается хорошо и что "
        "можно улучшить. Разбор откроет сессию, после него можно задать вопросы.",
        [[views.button(labels[days], f"rv:{days}") for days in REVIEW_PERIODS]],
    )


def start_review(
    db: Session, user: User, days: int, status_message_id: int | None = None
) -> tuple[AiJob, bool]:
    """Queues the assistant's review of the last `days` days in a session (a new one if
    needed, so follow-up questions work). -> (job, whether a session was started)."""
    if days not in REVIEW_PERIODS:
        raise DomainError("Такого периода нет")
    if get_settings().ai_runner == "off":
        raise DomainError(ERRORS["off"])
    session, started = sessions.ensure(db, user)
    sessions.touch(session)
    message = ChatMessage(
        user_id=user.id,
        role="user",
        text=f"Разбор рациона за {REVIEW_PERIODS[days]}",
        session_id=session.id,
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
    return job, started


def _press(db: Session, user: User, parts: list[str], message_id: int | None) -> dict:
    head = parts[0]
    result = {"view": None, "toast": None, "message": None, "job_id": None}
    if head == "s":
        return _press_session(db, user, parts, result)
    if head == "aw":
        state_of(db, user).awaiting = None
        db.commit()
        result["view"] = view("Хорошо, отменил.")
        return result
    if head == "h":
        result["message"] = help_view(db, user)
        return result
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
    if head == "n":
        return _press_note(db, user, parts, result)
    if head == "rv":
        days = int(parts[1])
        job, started = start_review(db, user, days)
        db.commit()
        result["job_id"] = job.id
        result["view"] = view(f"⏳ Разбираю рацион за {REVIEW_PERIODS[days]}…")
        if started:
            result["message"] = sessions.started_view(db, user)
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
            # A fix is said in words to the assistant: that takes a session.
            session, started = sessions.ensure(db, user)
            sessions.touch(session)
            state = state_of(db, user)
            state.focus_meal_id = meal.id
            db.commit()
            ask = (
                f"✏️ Что исправить в «{escape(meal.title)}»? Напишите, например: "
                "<i>«риса было 200 г»</i>, <i>«без соуса»</i> или <i>«это был ужин»</i>."
            )
            if started:
                start_view = sessions.started_view(db, user)
                result["message"] = {**start_view, "text": f"{start_view['text']}\n\n{ask}"}
            else:
                result["message"] = view(ask)
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
            _note_answer(db, user, f"(Пользователь нажал «Нет») {action.summary} → не изменено")
            db.commit()
            result["view"] = view(f"{escape(action.summary)}\n\n✖️ Хорошо, ничего не меняю.")
            return result
        done = execute_pending(db, user, action, parts[1] if head == "a" else "y")
        action.status = "done"
        _note_answer(db, user, f"(Пользователь нажал кнопку) {action.summary} → {done}")
        db.commit()
        if action.kind in ("edit_meal", "restore_meal"):
            # The meal card again, as it is now.
            meal = _meal(db, user, str(action.payload["meal_id"]))
            lines = action.payload["plan"]["lines"] if action.kind == "edit_meal" else None
            result["view"] = _meal_view(db, user, meal, changes=lines)
            result["toast"] = "Исправлено" if action.kind == "edit_meal" else "Вернул как было"
            return result
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
        result["view"] = view("Хорошо, это отменил.")
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


def _press_session(db: Session, user: User, parts: list[str], result: dict) -> dict:
    """s:go:<message> starts a session with a message sent outside one; s:pr:<message>
    files its photos as progress photos instead."""
    message = db.get(ChatMessage, int(parts[2]))
    if (
        not message
        or message.user_id != user.id
        or message.session_id
        or message.created_at < utcnow() - timedelta(days=1)
    ):
        raise DomainError("Сообщение уже обработано или устарело")
    if parts[1] == "pr":
        photos = db.scalars(
            select(Media).where(Media.message_id == message.id, Media.kind == "chat")
        ).all()
        if not photos:
            raise DomainError("В сообщении нет фото")
        answered = _save_progress(db, user, list(photos), message.text, None)
        result["view"] = answered["view"]
        return result
    if get_settings().ai_runner == "off":
        raise DomainError(ERRORS["off"])
    session, started = sessions.ensure(db, user)
    sessions.touch(session)
    message.session_id = session.id
    job = queue_turn(db, user, message)
    job.not_before = utcnow()
    result["message"] = sessions.started_view(db, user) if started else None
    db.commit()
    # The question is answered: it goes away, the message gets 👀 like any in a session.
    result["job_id"] = job.id
    result["delete"] = True
    result["react_to"] = message.telegram_message_id
    return result


def _press_note(db: Session, user: User, parts: list[str], result: dict) -> dict:
    """n:t:<id>:<code> moves a note to another meal, n:x:<id> drops it, n:go:<id> asks
    the assistant to log the meal from it now (in a session)."""
    note = notes.usable(db, int(parts[2]), user.id)
    if parts[1] == "t":
        notes.place(note, {**views.TYPE_CODES, "x": None}[parts[3]], user)
        db.commit()
        result["view"] = views.note_view(note, user.profile.timezone)
        return result
    if parts[1] == "x":
        note.status = "deleted"
        db.commit()
        result["view"] = view(f"🗑 Заметка удалена\n<s>{escape(note.text)}</s>")
        return result
    if get_settings().ai_runner == "off":
        raise DomainError(ERRORS["off"])
    session, started = sessions.ensure(db, user)
    sessions.touch(session)
    message = ChatMessage(
        user_id=user.id,
        role="user",
        text=f"Запиши по заметке [note {note.id}]:\n{note.text}",
        session_id=session.id,
    )
    db.add(message)
    db.flush()
    job = queue_turn(db, user, message)
    job.not_before = utcnow()
    db.commit()
    result["view"] = view(f"▶️ Считаю по заметке\n{escape(note.text)}")
    result["message"] = sessions.started_view(db, user) if started else None
    result["job_id"] = job.id
    return result


def pending_jobs(db: Session, user: User) -> int:
    return len(
        db.scalars(
            select(AiJob.id).where(
                AiJob.user_id == user.id, AiJob.status.in_(["queued", "running"])
            )
        ).all()
    )
