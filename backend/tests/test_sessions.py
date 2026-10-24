"""Sessions in the bot: only messages inside one reach the assistant."""

import asyncio
import io
from datetime import timedelta

import pytest
from conftest import jpeg
from PIL import Image
from sqlalchemy import select

from app.ai.models import AiJob
from app.chat import sessions as chat_sessions
from app.chat.models import ChatSession, ChatState, OutboxMessage
from app.database import utcnow

OK = {"reply": "Понял", "actions": []}


@pytest.fixture
def person(make_person):
    return make_person(9401, "Вадим")


def drain(worker):
    asyncio.run(worker.drain())


def test_outside_a_session_nothing_reaches_the_assistant(person, runner, worker, sessions):
    answer = person.say("что съесть на ужин?", telegram_message_id=321).json()
    assert answer["job_id"] is None and "Сессия не начата" in answer["view"]["text"]
    go = answer["view"]["buttons"][0][0]["data"]
    assert go.startswith("s:go:")
    drain(worker)
    assert runner.calls == []

    # One tap: a session starts and the message goes to the assistant; the question
    # goes away and the message gets 👀 like any other in a session.
    runner.answers.append(OK)
    pressed = person.press(go)
    assert pressed["job_id"] and pressed["delete"] and pressed["view"] is None
    assert pressed["react_to"] == 321
    assert pressed["message"]["keyboard"][0][0] == chat_sessions.END
    assert pressed["message"]["placeholder"] == "Сообщение ассистенту…"
    drain(worker)
    assert "что съесть на ужин?" in runner.calls[0]["prompt"]
    assert person.press(go)["toast"] == "Сообщение уже обработано или устарело"


def test_photo_outside_a_session_can_be_a_progress_photo(person):
    answer = person.say(photos=[jpeg(), jpeg()]).json()
    rows = answer["view"]["buttons"]
    assert rows[1][0]["data"].startswith("s:pr:")
    assert person.press(rows[1][0]["data"])["view"]["text"].startswith("📸 Сохранил")
    [entry] = person.web.get("/api/progress-entries").json()
    assert len(entry["photos"]) == 2


def test_a_quick_row_is_answered_at_once(person, runner, worker):
    started = person.say(chat_sessions.NEW).json()["view"]
    assert "Сессия началась" in started["text"]
    assert started["keyboard"][0][0] == chat_sessions.END
    first = person.say("на обед был суп", photos=[jpeg()]).json()
    second = person.say("и еще хлеб", photos=[jpeg(color=(20, 90, 200))]).json()
    assert first["job_id"] == second["job_id"]
    runner.answers.append(OK)
    drain(worker)
    [call] = runner.calls
    assert "Новые сообщения пользователя (2" in call["prompt"]
    assert "на обед был суп" in call["prompt"] and "и еще хлеб" in call["prompt"]
    assert "Фото 1: новое" in call["prompt"] and "Фото 2: новое" in call["prompt"]
    assert len(call["images"]) == 2

    # The next turn still sees those photos, small, and the earlier conversation.
    runner.answers.append(OK)
    person.say("а сколько там белка?")
    drain(worker)
    later = runner.calls[1]
    assert "раньше в этой сессии (уменьшено)" in later["prompt"]
    assert "[фото: 1]: на обед был суп" in later["prompt"]
    assert "## Новое сообщение пользователя" in later["prompt"]
    assert len(later["images"]) == 2
    assert max(Image.open(io.BytesIO(later["images"][0])).size) <= 512


def test_numbers_are_recorded_without_the_assistant(person, runner, worker):
    assert "Записал вес: 82,4" in person.say("82,4").json()["view"]["text"]
    saved = person.say("талия 82, бедра 98,5").json()["view"]["text"]
    assert "талия 82 см" in saved and "бедра 98,5 см" in saved
    # A question that mentions a measurement is not a measurement.
    assert "Сессия не начата" in person.say("талия 82 это нормально?").json()["view"]["text"]
    # After "⚖️ Вес": a typo with digits asks again, words mean the person moved on.
    assert "Пришлите вес" in person.say(chat_sessions.WEIGHT).json()["view"]["text"]
    assert "Не похоже на вес" in person.say("8l,2").json()["view"]["text"]
    person.say(chat_sessions.WEIGHT)
    assert "Сессия не начата" in person.say("а что на ужин?").json()["view"]["text"]

    # Inside a session too, and the assistant does not see them as new messages.
    person.start_session()
    person.say("грудь 101")
    runner.answers.append(OK)
    person.say("как дела с замерами?")
    drain(worker)
    new = runner.calls[0]["prompt"].split("## Новое сообщение")[1]
    assert "как дела с замерами?" in new and "грудь 101" not in new


def test_once_a_day(person, runner, worker, sessions):
    person.say("82,4")
    person.say(chat_sessions.WEIGHT)
    asked = person.say("81").json()["view"]
    assert asked["text"].startswith("❓ Вес сегодня уже записан: 82,4 кг")
    replace, keep = asked["buttons"][0][0]["data"], asked["buttons"][1][0]["data"]
    assert replace.startswith("a:y:") and keep.startswith("a:n:")
    assert "Вес заменен: 81 кг" in person.press(replace)["view"]["text"]
    assert [w["weight_kg"] for w in person.web.get("/api/weights").json()] == [81]

    person.say("талия 82, бедра 98")
    mixed = person.say("талия 81, грудь 100").json()["view"]
    assert "Записал: грудь 100 см" in mixed["text"]
    assert "заменить талия 82 → 81 см" in mixed["text"]
    assert "ничего не меняю" in person.press(mixed["buttons"][1][0]["data"])["view"]["text"]
    waist = [m for m in person.web.get("/api/measurements").json() if m["kind"] == "waist"]
    assert [m["value"] for m in waist] == [82]

    person.say("прогресс", photos=[jpeg(), jpeg()])
    again = person.say("прогресс", photos=[jpeg()]).json()["view"]
    assert "уже есть (2)" in again["text"]
    assert again["buttons"][0][1]["data"].startswith("a:add:")
    assert "Добавил" in person.press(again["buttons"][0][1]["data"])["view"]["text"]
    [entry] = person.web.get("/api/progress-entries").json()
    assert sorted(p["pose"] for p in entry["photos"]) == ["back", "front", "side"]
    third = person.say("прогресс", photos=[jpeg()]).json()["view"]
    assert "Фото заменены" in person.press(third["buttons"][0][0]["data"])["view"]["text"]
    [entry] = person.web.get("/api/progress-entries").json()
    assert [p["pose"] for p in entry["photos"]] == ["front"]

    # The assistant follows the same rule.
    person.start_session()
    runner.answers.append(
        {"reply": "", "actions": [{"kind": "log_weight", "weight_kg": 80.5, "measured_at": None}]}
    )
    person.say("взвесился, 80,5 вроде")
    drain(worker)
    with sessions() as db:
        card = db.scalars(select(OutboxMessage)).all()[-1].payload
        assert "Вес сегодня уже записан: 81 кг" in card["text"]
        assert card["buttons"][0][0]["text"] == "🔁 Заменить"
    assert len(person.web.get("/api/weights").json()) == 1


def test_ending_a_session_sums_it_up(person, runner, worker):
    person.start_session()
    person.say("вес 80")  # recorded by the bot, still counts for the session
    ended = person.say(chat_sessions.END).json()["view"]
    assert "Сессия закрыта" in ended["text"] and "⚖️ Вес 80 кг" in ended["text"]
    assert ended["keyboard"][0][0] == chat_sessions.NEW
    assert ended["styles"] == {chat_sessions.NEW: "success"}
    assert person.say(chat_sessions.END).json()["view"]["text"] == "Сессия уже закрыта."


def test_quiet_sessions_close_by_themselves(person, sessions):
    person.start_session()
    with sessions() as db:
        session = db.scalar(select(ChatSession))
        session.last_activity_at = utcnow() - timedelta(minutes=61)
        db.commit()
        assert chat_sessions.close_idle(db) == 1
        [message] = db.scalars(select(OutboxMessage)).all()
        assert "час тишины" in message.payload["text"]
        assert "Ничего не записали" in message.payload["text"]
        assert message.payload["keyboard"][0][0] == chat_sessions.NEW
    assert "Сессия не начата" in person.say("привет").json()["view"]["text"]


def test_typing_while_the_assistant_works(person, runner, worker):
    person.start_session()
    person.say("что на ужин?")
    assert person.telegram_id in person.bot.get("/api/bot/typing").json()
    runner.answers.append(OK)
    drain(worker)
    assert person.bot.get("/api/bot/typing").json() == []


def test_fix_button_opens_a_session(person, sessions):
    meal = person.web.post(
        "/api/meals", json={"title": "Суп", "items": [{"name": "Суп", "kcal": 200}]}
    ).json()
    pressed = person.press(f"m:e:{meal['id']}")
    assert "Сессия началась" in pressed["message"]["text"]
    assert "Что исправить в «Суп»" in pressed["message"]["text"]
    with sessions() as db:
        assert db.scalar(select(ChatSession)).ended_at is None
        assert db.scalars(select(AiJob)).all() == []


def test_people_get_the_new_keyboard_once(person, sessions):
    with sessions() as db:
        for state in db.scalars(select(ChatState)):
            state.keyboard_version = 0  # as before the update
        db.commit()
    person.say("82,4")
    person.say("82,5")
    with sessions() as db:
        notes = [
            m for m in db.scalars(select(OutboxMessage)) if "Бот обновился" in m.payload["text"]
        ]
        assert len(notes) == 1 and notes[0].payload["keyboard"][0][0] == chat_sessions.NEW


def test_the_diary_opens_inside_telegram(person):
    more = person.say(chat_sessions.MORE).json()["view"]
    assert more["buttons"][0][0] == {
        "text": "🌐 Открыть дневник",
        "web_app": "https://food.example.com/",
    }
    today = person.say(chat_sessions.TODAY).json()["view"]
    assert today["buttons"][0][0]["web_app"].startswith("https://food.example.com")
