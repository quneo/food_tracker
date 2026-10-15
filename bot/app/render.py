"""Server-made views -> Telegram messages.

A view is {"text": html, "buttons": [[{"text", "data" | "url" | "web_app", "style"?}]],
"keyboard": [[label]]?, "placeholder"?, "styles": {label: style}?}; the backend builds them
so every rule stays next to the data. "keyboard" replaces the keyboard under the input
field (its taps come back as plain text messages); "placeholder" is the hint in the empty
input field. A style colours a button: "success", "danger" or "primary"."""

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
STYLES = {"success", "danger", "primary"}


def _style(value) -> str | None:
    return value if value in STYLES else None


def markup(view: dict) -> InlineKeyboardMarkup | ReplyKeyboardMarkup | None:
    if view.get("keyboard"):
        styles = view.get("styles") or {}
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=label, style=_style(styles.get(label))) for label in row]
                for row in view["keyboard"]
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder=(view.get("placeholder") or "")[:64] or None,
        )
    rows = []
    for row in view.get("buttons") or []:
        buttons = []
        for button in row:
            if not button:
                continue
            style = _style(button.get("style"))
            if button.get("web_app"):
                # The diary inside Telegram, signed in with the Mini App data.
                buttons.append(
                    InlineKeyboardButton(
                        text=button["text"], web_app=WebAppInfo(url=button["web_app"]), style=style
                    )
                )
            elif button.get("url"):
                buttons.append(
                    InlineKeyboardButton(text=button["text"], url=button["url"], style=style)
                )
            else:
                buttons.append(
                    InlineKeyboardButton(
                        text=button["text"], callback_data=button["data"], style=style
                    )
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
