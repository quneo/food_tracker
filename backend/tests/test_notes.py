"""Weigh notes: grams written down now, waiting for the meal they belong to."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import jpeg
from sqlalchemy import select

from app.chat import sessions as chat_sessions
from app.chat.models import OutboxMessage
from app.notes import service as notes

TZ = ZoneInfo("Asia/Krasnoyarsk")
LUNCH = {
    "title": "Курица с рисом",
    "meal_type": "lunch",
    "eaten_at": None,
    "items": [
        {
            "name": "Куриная грудка запеченная",
            "product_id": None,
            "grams": 130,
            "grams_source": "stated",
            "kcal": 215,
            "protein": 40,
            "fat": 5,
            "carbs": 0,
            "confidence": "high",
            "note": None,
        }
    ],
    "kcal_low": 200,
    "kcal_high": 240,
    "confidence": "high",
    "assumptions": [],
    "comment": None,
}


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=TZ)


@pytest.mark.parametrize(
    ("meal", "now", "due", "burns"),
    [
        # Weighed in the evening for lunch: tomorrow's lunch, an hour before it starts.
        ("lunch", at(20, 21), at(21, 10), at(21, 18)),
        # In the morning for lunch: today's.
        ("lunch", at(20, 8), at(20, 10), at(20, 18)),
        # During lunch: it is time already.
        ("lunch", at(20, 12, 30), at(20, 12, 30), at(20, 18)),
        ("dinner", at(20, 23, 30), at(21, 15), at(22, 1)),
        # Soon: three hours.
        (None, at(20, 12), at(20, 12), at(20, 15)),
        ("snack", at(20, 9), at(20, 9), at(20, 21)),
    ],
)
def test_a_note_waits_for_the_next_meal_of_its_kind(meal, now, due, burns):
    assert notes.window(meal, now) == (due, burns)


def run_jobs(worker):
    asyncio.run(worker.drain())


@pytest.fixture
def person(make_person):
    return make_person(7101, "Вадим")


def test_notes_on_the_site(person):
    created = person.web.post(
        "/api/notes", json={"text": " 130 грудка\n\n150   рис ", "meal_type": "lunch"}
    )
    assert created.status_code == 201
    note = created.json()
    assert note["text"] == "130 грудка\n150 рис" and note["label"].startswith("на обед")
    moved = person.web.patch(f"/api/notes/{note['id']}", json={"meal_type": None}).json()
    assert moved["due"] and moved["label"].startswith("на ближайшие часы, до ")
    assert [item["id"] for item in person.web.get("/api/notes").json()] == [note["id"]]
    assert person.web.delete(f"/api/notes/{note['id']}").status_code == 204
    assert person.web.get("/api/notes").json() == []
    assert person.web.post("/api/notes", json={"text": "  "}).status_code == 400


def test_a_note_in_the_bot_never_reaches_the_assistant(person, runner, worker):
    person.start_session()
    answer = person.say("Заметка на ужин: 130 грудка\n150 рис").json()
    assert answer["job_id"] is None
    card = answer["view"]
    assert "Заметка сохранена" in card["text"] and "на ужин" in card["text"]
    [note] = person.web.get("/api/notes").json()
    assert note["text"] == "130 грудка\n150 рис" and note["meal_type"] == "dinner"
    targets = [button["data"] for row in card["buttons"] for button in row]
    assert f"n:t:{note['id']}:d" in targets and f"n:go:{note['id']}" in targets

    moved = person.press(f"n:t:{note['id']}:b")["view"]
    assert "на завтрак" in moved["text"] and "✓ 🍳 Завтрак" in str(moved["buttons"])

    # The key asks, the next message is the note (for soon when no meal is named).
    asked = person.say(chat_sessions.NOTE).json()["view"]
    assert "Пришлите, что взвесили" in asked["text"] and "Уже ждут" in asked["text"]
    person.say("200 творог")
    # The order follows when each one is due, which depends on the time of the test.
    waiting = person.web.get("/api/notes").json()
    assert sorted(item["meal_type"] or "soon" for item in waiting) == ["breakfast", "soon"]
    assert runner.calls == []

    person.press(f"n:x:{note['id']}")
    assert len(person.web.get("/api/notes").json()) == 1
    assert "Ждут учета" in person.bot.get("/api/bot/today").json()["view"]["text"]


def test_the_assistant_logs_a_meal_from_a_note(person, runner, worker, sessions):
    note = person.web.post("/api/notes", json={"text": "130 грудка", "meal_type": None}).json()
    started = person.start_session()
    # Its time has come: the session says so.
    assert "130 грудка" in started["text"] and "по заметке" in started["text"]
    runner.answers.append(
        {
            "reply": "",
            "actions": [
                {
                    "kind": "create_meal",
                    "meal": LUNCH,
                    "use_photos": False,
                    "note_id": note["id"],
                },
                {"kind": "save_note", "text": "150 творог", "meal_type": "snack"},
            ],
        }
    )
    person.say("обед по заметке, а творог съем потом")
    run_jobs(worker)
    prompt = runner.calls[0]["prompt"]
    assert "## Заметки о взвешивании" in prompt
    assert f"[note {note['id']}] на ближайшие часы" in prompt and "(пора" in prompt
    waiting = person.web.get("/api/notes").json()
    assert [item["text"] for item in waiting] == ["150 творог"]
    with sessions() as db:
        [message] = db.scalars(select(OutboxMessage)).all()
    assert "📝 Заметка на перекус" in message.payload["text"]


def test_log_now_from_the_note_card(person, runner, worker):
    note = person.web.post("/api/notes", json={"text": "130 грудка"}).json()
    pressed = person.press(f"n:go:{note['id']}")
    assert pressed["job_id"] and "Сессия началась" in pressed["message"]["text"]
    runner.answers.append(
        {
            "reply": "",
            "actions": [
                {"kind": "create_meal", "meal": LUNCH, "use_photos": False, "note_id": note["id"]}
            ],
        }
    )
    run_jobs(worker)
    assert f"Запиши по заметке [note {note['id']}]" in runner.calls[0]["prompt"]
    assert person.web.get("/api/notes").json() == []


def test_a_site_meal_from_a_note_uses_it_up(person, runner, worker):
    note = person.web.post("/api/notes", json={"text": "130 грудка", "meal_type": "lunch"}).json()
    runner.answers.append(
        {"reply": "", "actions": [{"kind": "create_meal", "meal": LUNCH, "use_photos": True}]}
    )
    started = person.web.post(
        "/api/assistant/meals",
        data={"text": note["text"], "note_id": str(note["id"])},
        files=[("photos", ("p.jpg", jpeg(), "image/jpeg"))],
    )
    assert started.status_code == 202
    run_jobs(worker)
    assert person.web.get("/api/notes").json() == []
    stale = person.web.post(
        "/api/assistant/meals", data={"text": "ещё", "note_id": str(note["id"])}
    )
    assert stale.status_code == 400
