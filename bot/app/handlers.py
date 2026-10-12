"""Telegram updates -> backend. The backend decides what a message means: a tap on the
keyboard under the input field, a weight, a message for the assistant in a session."""

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, CallbackQuery, Message

from app.api import ApiError, backend
from app.delivery import send

router = Router()
log = logging.getLogger(__name__)

ALBUM_WAIT = 1.2  # seconds to collect the photos of one album
MAX_PHOTOS = 6
COMMANDS = [
    BotCommand(command="new", description="Новая сессия с ассистентом"),
    BotCommand(command="end", description="Завершить сессию"),
    BotCommand(command="today", description="Итоги дня"),
    BotCommand(command="review", description="Разбор рациона"),
    BotCommand(command="progress", description="Сохранить фото прогресса"),
    BotCommand(command="app", description="Дневник на сайте"),
    BotCommand(command="link", description="Привязать Telegram ключом с сайта"),
    BotCommand(command="help", description="Как пользоваться"),
]
albums: dict[str, list[Message]] = {}
background: set[asyncio.Task] = set()


def keep(task: asyncio.Task):
    background.add(task)
    task.add_done_callback(background.discard)


def profile(message: Message) -> dict:
    user = message.from_user
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "language_code": user.language_code,
    }


async def reply(message: Message, bot: Bot, call, *args, **kwargs):
    """Runs a backend call that returns {"view"} and shows the view."""
    try:
        result = await call(*args, **kwargs)
        view = result["view"]
    except ApiError as error:
        view = {"text": str(error)}
    await send(bot, message.chat.id, view)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, bot: Bot):
    await reply(
        message,
        bot,
        backend.call,
        "POST",
        "bot/start",
        json={"user": profile(message), "payload": command.args},
    )


@router.message(Command("help"))
async def help_(message: Message, bot: Bot):
    await reply(message, bot, backend.call, "GET", "bot/help", message.from_user.id)


@router.message(Command("today"))
async def today(message: Message, bot: Bot):
    await reply(message, bot, backend.call, "GET", "bot/today", message.from_user.id)


@router.message(Command("review"))
async def review(message: Message, bot: Bot):
    await reply(message, bot, backend.call, "GET", "bot/review", message.from_user.id)


@router.message(Command("new"))
async def new(message: Message, bot: Bot):
    await reply(message, bot, backend.call, "POST", "bot/new", message.from_user.id)


@router.message(Command("end"))
async def end(message: Message, bot: Bot):
    await reply(message, bot, backend.call, "POST", "bot/end", message.from_user.id)


@router.message(Command("progress"))
async def progress(message: Message, bot: Bot):
    await reply(message, bot, backend.call, "POST", "bot/progress-mode", message.from_user.id)


@router.message(Command("app"))
async def app_link(message: Message, bot: Bot):
    await reply(message, bot, backend.call, "GET", "bot/app", message.from_user.id)


@router.message(Command("link"))
async def link(message: Message, command: CommandObject, bot: Bot):
    """/link <key>: the one-time key from the site's profile attaches this Telegram."""
    await reply(
        message,
        bot,
        backend.call,
        "POST",
        "bot/link",
        json={"user": profile(message), "code": command.args},
    )


async def forward(messages: list[Message], bot: Bot):
    """Sends a message (or an album) to the backend. A quick answer comes back at once;
    the assistant's answer comes through the outbox, with "typing…" shown meanwhile."""
    first = messages[0]
    photos = [
        m
        for m in messages
        if m.photo or (m.document and m.document.mime_type or "").startswith("image/")
    ]
    text = next((m.text or m.caption for m in messages if m.text or m.caption), "") or ""
    if photos:
        await bot.send_chat_action(first.chat.id, "upload_photo")
    try:
        files = []
        for number, item in enumerate(photos[:MAX_PHOTOS]):
            file_id = item.photo[-1].file_id if item.photo else item.document.file_id
            content = await bot.download(file_id)
            files.append(("photos", (f"{number}.jpg", content.read(), "image/jpeg")))
        result = await backend.call(
            "POST",
            "bot/messages",
            first.from_user.id,
            data={"text": text, "telegram_message_id": str(first.message_id)},
            files=files or None,
        )
        if result.get("view"):
            await send(bot, first.chat.id, result["view"])
        elif result.get("job_id"):
            await bot.send_chat_action(first.chat.id, "typing")
        if len(photos) > MAX_PHOTOS:
            await first.answer(f"Взял первые {MAX_PHOTOS} фото из {len(photos)}.")
    except ApiError as error:
        await send(bot, first.chat.id, {"text": str(error)})
    except Exception:
        log.exception("forwarding failed")
        await send(
            bot, first.chat.id, {"text": "Не получилось обработать сообщение. Попробуйте еще раз."}
        )


async def collect_album(group_id: str, bot: Bot):
    await asyncio.sleep(ALBUM_WAIT)
    await forward(albums.pop(group_id), bot)


@router.message(F.photo | (F.document & F.document.mime_type.startswith("image/")))
async def photo(message: Message, bot: Bot):
    if not message.media_group_id:
        keep(asyncio.create_task(forward([message], bot)))
        return
    # An album arrives as separate messages: gather them and send them together.
    group = albums.setdefault(message.media_group_id, [])
    group.append(message)
    if len(group) == 1:
        keep(asyncio.create_task(collect_album(message.media_group_id, bot)))


@router.message(F.text & ~F.text.startswith("/"))
async def text(message: Message, bot: Bot):
    # A task, so a slow upload never holds the next update.
    keep(asyncio.create_task(forward([message], bot)))


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message, bot: Bot):
    await send(bot, message.chat.id, {"text": "Такой команды нет. /help — что я умею."})


@router.message()
async def other(message: Message, bot: Bot):
    await send(
        bot,
        message.chat.id,
        {"text": "Пока я понимаю текст и фото 🙂 Опишите словами или пришлите снимок."},
    )


@router.callback_query(F.data)
async def press(callback: CallbackQuery, bot: Bot):
    try:
        message_id = callback.message.message_id if callback.message else None
        result = await backend.call(
            "POST",
            "bot/press",
            callback.from_user.id,
            json={"data": callback.data, "message_id": message_id},
        )
    except ApiError as error:
        await callback.answer(str(error)[:200], show_alert=True)
        return
    toast = result.get("toast")
    await callback.answer(
        toast[:200] if toast else None, show_alert=bool(toast and len(toast) > 60)
    )
    message = callback.message
    if result.get("view") and message:
        await send(bot, message.chat.id, result["view"], message.message_id)
    if result.get("message") and message:
        await send(bot, message.chat.id, result["message"])
    if result.get("job_id") and message:
        await bot.send_chat_action(message.chat.id, "typing")
