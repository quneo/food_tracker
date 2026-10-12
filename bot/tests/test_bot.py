import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import EditMessageText, SendMessage

from app import render
from app.api import ApiError, Backend
from app.delivery import deliver_once, send

VIEW = {
    "text": "🍽 <b>Курица с рисом</b>",
    "buttons": [
        [{"text": "✅ Сохранить", "data": "m:ok:1"}, {"text": "✏️ Исправить", "data": "m:e:1"}],
        [None],
        [{"text": "Открыть в дневнике", "url": "https://food.example.com/diary?meal=1"}],
    ],
}


def fake_bot(edit_error=None, send_error=None):
    bot = SimpleNamespace(
        edit_message_text=AsyncMock(side_effect=edit_error),
        send_message=AsyncMock(side_effect=send_error, return_value=SimpleNamespace(message_id=42)),
    )
    return bot


def bad_request(text):
    return TelegramBadRequest(method=EditMessageText(text="x"), message=text)


def test_markup_from_view():
    keyboard = render.markup(VIEW)
    assert [[b.text for b in row] for row in keyboard.inline_keyboard] == [
        ["✅ Сохранить", "✏️ Исправить"],
        ["Открыть в дневнике"],
    ]
    assert keyboard.inline_keyboard[0][0].callback_data == "m:ok:1"
    assert keyboard.inline_keyboard[1][0].url.endswith("meal=1")
    assert render.markup({"text": "x"}) is None


def test_long_text_becomes_plain():
    body, mode = render.text({"text": "<b>а</b> &amp; " * 1000})
    assert mode is None and len(body) <= 4096 and "<b>" not in body and "&" in body
    assert render.text({"text": "<b>ok</b>"}) == ("<b>ok</b>", "HTML")


async def test_send_edits_or_falls_back_to_new_message():
    bot = fake_bot()
    assert await send(bot, 7, VIEW, edit_message_id=5) == 5
    bot.send_message.assert_not_awaited()

    gone = fake_bot(edit_error=bad_request("message to edit not found"))
    assert await send(gone, 7, VIEW, edit_message_id=5) == 42
    gone.send_message.assert_awaited_once()

    same = fake_bot(edit_error=bad_request("message is not modified"))
    assert await send(same, 7, VIEW, edit_message_id=5) == 5


def backend_with(handler):
    return Backend("http://backend.test/api", transport=httpx.MockTransport(handler))


async def test_outbox_delivery_reports_back():
    reports = {}

    def handler(request: httpx.Request):
        assert request.headers["X-Bot-Secret"] == "test-bot-secret-" * 3
        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {"id": 1, "chat_id": 7, "text": "Привет", "buttons": [], "edit_message_id": 3},
                    {"id": 2, "chat_id": 8, "text": "⏰ Пить воду", "buttons": []},
                ],
            )
        reports[request.url.path] = json.loads(request.content)
        return httpx.Response(200, json={"status": "sent"})

    blocked = TelegramForbiddenError(method=SendMessage(chat_id=8, text="x"), message="blocked")
    bot = fake_bot(send_error=[blocked])
    assert await deliver_once(bot, backend_with(handler)) == 2
    assert reports["/api/bot/outbox/1"] == {"message_id": 3}
    assert reports["/api/bot/outbox/2"]["permanent"] is True


async def test_backend_errors_are_readable():
    def handler(request):
        if request.url.path.endswith("missing"):
            return httpx.Response(401, json={"detail": {"code": "x"}})
        return httpx.Response(403, json={"detail": "Доступ закрыт"})

    backend = backend_with(handler)
    with pytest.raises(ApiError) as missing:
        await backend.call("GET", "bot/missing", 1)
    assert missing.value.status == 401 and "/start" in str(missing.value)
    with pytest.raises(ApiError, match="Доступ закрыт"):
        await backend.call("GET", "bot/today", 1)


def test_keyboard_under_the_input_field():
    keyboard = render.markup({"text": "x", "keyboard": [["🟢 Новая сессия", "📊 Сегодня"]]})
    assert [[b.text for b in row] for row in keyboard.keyboard] == [
        ["🟢 Новая сессия", "📊 Сегодня"]
    ]
    assert keyboard.resize_keyboard and keyboard.is_persistent


async def test_a_keyboard_message_is_sent_not_edited():
    bot = fake_bot()
    view = {"text": "🟢 Сессия началась", "keyboard": [["⏹ Завершить сессию"]]}
    assert await send(bot, 7, view, edit_message_id=5) == 42
    bot.edit_message_text.assert_not_awaited()


async def test_typing_is_shown_while_the_assistant_works():
    from app.delivery import show_typing

    bot = SimpleNamespace(send_chat_action=AsyncMock())
    backend = SimpleNamespace(call=AsyncMock(return_value=[7, 8]))
    shown: dict[int, float] = {}
    await show_typing(bot, backend, shown)
    await show_typing(bot, backend, shown)  # not again within a few seconds
    assert bot.send_chat_action.await_count == 2
    assert {call.args for call in bot.send_chat_action.await_args_list} == {
        (7, "typing"),
        (8, "typing"),
    }


def test_diary_opens_inside_telegram():
    keyboard = render.markup(
        {
            "text": "x",
            "buttons": [[{"text": "🌐 Открыть дневник", "web_app": "https://food.example.com/"}]],
        }
    )
    button = keyboard.inline_keyboard[0][0]
    assert button.web_app.url == "https://food.example.com/" and button.url is None
