"""Server-made views -> Telegram messages.

A view is {"text": html, "buttons": [[{"text", "data" | "url"}]]}; the backend builds them
so every rule stays next to the data."""

import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

LIMIT = 4096
TAG = re.compile(r"<[^>]+>")


def markup(view: dict) -> InlineKeyboardMarkup | None:
    rows = []
    for row in view.get("buttons") or []:
        buttons = []
        for button in row:
            if not button:
                continue
            if button.get("url"):
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
