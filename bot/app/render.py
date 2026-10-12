"""Server-made views -> Telegram messages.

A view is {"text": html, "buttons": [[{"text", "data" | "url"}]], "keyboard": [[label]]?};
the backend builds them so every rule stays next to the data. "keyboard" replaces the
keyboard under the input field (its taps come back as plain text messages)."""

import re

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

LIMIT = 4096
TAG = re.compile(r"<[^>]+>")


def markup(view: dict) -> InlineKeyboardMarkup | ReplyKeyboardMarkup | None:
    if view.get("keyboard"):
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=label) for label in row] for row in view["keyboard"]],
            resize_keyboard=True,
            is_persistent=True,
        )
    rows = []
    for row in view.get("buttons") or []:
        buttons = []
        for button in row:
            if not button:
                continue
            if button.get("web_app"):
                # The diary inside Telegram, signed in with the Mini App data.
                buttons.append(
                    InlineKeyboardButton(
                        text=button["text"], web_app=WebAppInfo(url=button["web_app"])
                    )
                )
            elif button.get("url"):
                buttons.append(InlineKeyboardButton(text=button["text"], url=button["url"]))
            else:
                buttons.append(
                    InlineKeyboardButton(text=button["text"], callback_data=button["data"])
                )
        if buttons:
            rows.append(buttons)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def text(view: dict) -> tuple[str, str | None]:
    """-> (text, parse mode)."""
    body = view.get("text") or "…"
    if len(body) <= LIMIT:
        return body, "HTML"
    # Cutting HTML may break a tag: send the shortened text as plain text.
    return plain(body)[: LIMIT - 1] + "…", None


def plain(body: str) -> str:
    return (
        TAG.sub("", body)
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
    )
