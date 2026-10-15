"""Sending views to Telegram, and the outbox loop that delivers the backend's messages
(assistant answers, reminders)."""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import ReactionTypeEmoji

from app import render
from app.api import ApiError, Backend
from app.config import settings

log = logging.getLogger(__name__)


async def send(bot: Bot, chat_id: int, view: dict, edit_message_id: int | None = None) -> int:
    """Shows a view: edits the given message when possible, else sends a new one.
    Returns the id of the message that shows it."""
    body, parse_mode = render.text(view)
    keyboard = render.markup(view)
    # A message with the input-field keyboard can't be edited into place.
    if edit_message_id and not view.get("keyboard"):
        try:
            await bot.edit_message_text(
                body,
                chat_id=chat_id,
                message_id=edit_message_id,
                parse_mode=parse_mode,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return edit_message_id
        except TelegramBadRequest as error:
            if "message is not modified" in str(error):
                return edit_message_id
            if "can't parse entities" in str(error):
                return await send(bot, chat_id, {**view, "text": render.plain(body)}, None)
            # Too old or deleted: show it as a new message instead.
    try:
        message = await bot.send_message(
            chat_id,
            body,
            parse_mode=parse_mode,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as error:
        if "can't parse entities" not in str(error):
            raise
        message = await bot.send_message(
            chat_id, render.plain(body), parse_mode=None, reply_markup=keyboard
        )
    return message.message_id


async def react(bot: Bot, chat_id: int, message_id: int | None, emoji: str = "👀"):
    """Marks a person's message (👀 = the assistant has it); a failed mark is not worth an error."""
    if not message_id:
        return
    try:
        await bot.set_message_reaction(
            chat_id, message_id, reaction=[ReactionTypeEmoji(emoji=emoji)]
        )
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError):
        pass


async def deliver_once(bot: Bot, backend: Backend) -> int:
    """Delivers what the outbox holds now; returns how many messages were handled."""
    items = await backend.call("GET", "bot/outbox")
    for item in items:
        report = {}
        try:
            report["message_id"] = await send(
                bot, item["chat_id"], item, item.get("edit_message_id")
            )
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after)
            return len(items)
        except TelegramForbiddenError as error:
            # The person blocked the bot: no point in retrying.
            report = {"error": str(error)[:300], "permanent": True}
        except TelegramBadRequest as error:
            report = {"error": str(error)[:300], "permanent": True}
        except TelegramNetworkError as error:
            report = {"error": str(error)[:300]}
        await backend.call("POST", f"bot/outbox/{item['id']}", json=report)
    return len(items)


TYPING_EVERY = 4.5  # Telegram shows "typing…" for about five seconds


async def show_typing(bot: Bot, backend: Backend, shown: dict[int, float]):
    """Keeps "typing…" in the chats where the assistant is working on an answer."""
    now = asyncio.get_running_loop().time()
    for chat_id in await backend.call("GET", "bot/typing"):
        if now - shown.get(chat_id, 0) >= TYPING_EVERY:
            shown[chat_id] = now
            try:
                await bot.send_chat_action(chat_id, "typing")
            except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError):
                pass


async def outbox_loop(bot: Bot, backend: Backend):
    shown: dict[int, float] = {}
    while True:
        try:
            await deliver_once(bot, backend)
            await show_typing(bot, backend, shown)
        except ApiError as error:
            log.warning("outbox: %s", error)
        except Exception:
            log.exception("outbox delivery failed")
        await asyncio.sleep(settings.outbox_interval)
