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

from app import render
from app.api import ApiError, Backend
from app.config import settings

log = logging.getLogger(__name__)


async def send(bot: Bot, chat_id: int, view: dict, edit_message_id: int | None = None) -> int:
    """Shows a view: edits the given message when possible, else sends a new one.
    Returns the id of the message that shows it."""
    body, parse_mode = render.text(view)
    keyboard = render.markup(view)
    if edit_message_id:
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


async def outbox_loop(bot: Bot, backend: Backend):
    while True:
        try:
            await deliver_once(bot, backend)
        except ApiError as error:
            log.warning("outbox: %s", error)
        except Exception:
            log.exception("outbox delivery failed")
        await asyncio.sleep(settings.outbox_interval)
