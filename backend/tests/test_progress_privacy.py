"""Progress entries (a day's photos together), measurements in one go, the photo code,
reminders every few weeks."""

import io
from datetime import date, datetime, timedelta

import pytest
from conftest import jpeg
from PIL import Image
from sqlalchemy import select

from app.chat.models import OutboxMessage
from app.reminders import service as reminders
from app.reminders.models import Reminder


@pytest.fixture
def person(make_person):
    return make_person(9301, "Вадим")


def upload(person, day: str, pose: str):
    response = person.web.post(
        "/api/progress-photos",
        files={"photo": ("b.jpg", jpeg(), "image/jpeg")},
        data={"taken_on": day, "pose": pose},
    )
    assert response.status_code == 201, response.text
    return response.json()


def picture(response) -> tuple[str, tuple[int, int]]:
    return response.headers["content-type"], Image.open(io.BytesIO(response.content)).size


def test_a_days_photos_are_one_entry(person, files):
    back = upload(person, "2026-10-05", "back")
    front = upload(person, "2026-10-05", "front")
    upload(person, "2026-10-01", "front")
    entries = person.web.get("/api/progress-entries").json()
    assert [e["taken_on"] for e in entries] == ["2026-10-05", "2026-10-01"]
    assert [p["pose"] for p in entries[0]["photos"]] == ["front", "back"]
    assert back["entry_id"] == front["entry_id"] == entries[0]["id"]

    # A new date merges the entry into the one already on that day.
    merged = person.web.patch(
        f"/api/progress-entries/{entries[0]['id']}", json={"taken_on": "2026-10-01", "note": "утро"}
    ).json()
    assert merged["id"] == entries[1]["id"] and len(merged["photos"]) == 3
    assert merged["note"] == "утро"
    assert len(person.web.get("/api/progress-entries").json()) == 1

    # One photo moves to another day and makes its own entry; the last one takes it along.
    moved = person.web.patch(f"/api/progress-photos/{back['id']}", json={"taken_on": "2026-10-08"})
    assert moved.json()["taken_on"] == "2026-10-08"
    assert len(person.web.get("/api/progress-entries").json()) == 2
    person.web.delete(f"/api/progress-photos/{back['id']}")
    assert len(person.web.get("/api/progress-entries").json()) == 1

    assert person.web.delete(f"/api/progress-entries/{merged['id']}").status_code == 204
    assert person.web.get("/api/progress-entries").json() == []
    assert files.objects == {}


def test_bot_album_becomes_front_and_back(person):
    person.bot.post("/api/bot/progress-mode")
    assert person.say(photos=[jpeg(), jpeg()]).json()["view"]["text"].startswith("📸")
    [entry] = person.web.get("/api/progress-entries").json()
    assert sorted(p["pose"] for p in entry["photos"]) == ["back", "front"]


def test_measurements_in_one_go(person):
    saved = person.web.post(
        "/api/measurements/batch",
        json={"values": {"waist": 82.4, "hips": 98}, "measured_at": "2026-10-12T08:30"},
    )
    assert saved.status_code == 201, saved.text
    assert {(m["kind"], m["value"]) for m in saved.json()} == {("waist", 82.4), ("hips", 98)}
    assert {m["measured_at"] for m in saved.json()} == {"2026-10-12T08:30+07:00"}
    assert person.web.post("/api/measurements/batch", json={"values": {}}).status_code == 422


def test_photo_code_blurs_body_photos(person, sessions):
    photo = upload(person, "2026-10-05", "front")
    url = f"/api/media/{photo['media_id']}?size=original"
    assert picture(person.web.get(url)) == ("image/jpeg", (64, 48))
    assert person.web.get("/api/photo-lock").json()["enabled"] is False

    assert person.web.put("/api/photo-lock", json={"pin": "12"}).status_code == 400
    state = person.web.put("/api/photo-lock", json={"pin": "2468"}).json()
    assert state["enabled"] and not state["unlocked"]
    locked = person.web.get(url)
    assert picture(locked) == ("image/webp", (360, 270))
    assert locked.headers["cache-control"] == "private, no-store"

    wrong = person.web.post("/api/photo-lock/unlock", json={"pin": "1111"})
    assert wrong.status_code == 403 and "4" in wrong.json()["detail"]
    state = person.web.post("/api/photo-lock/unlock", json={"pin": "2468"}).json()
    assert state["unlocked"] and state["unlocked_until"]
    assert picture(person.web.get(url)) == ("image/jpeg", (64, 48))
    person.web.post("/api/photo-lock/lock")
    assert picture(person.web.get(url))[0] == "image/webp"

    # Changing the code needs the current one; five wrong codes close the input for a while.
    assert (
        person.web.put("/api/photo-lock", json={"pin": "1357", "current": "0000"}).status_code
        == 403
    )
    for _ in range(3):
        person.web.post("/api/photo-lock/unlock", json={"pin": "0000"})
    assert person.web.post("/api/photo-lock/unlock", json={"pin": "0000"}).status_code == 429
    assert person.web.post("/api/photo-lock/unlock", json={"pin": "2468"}).status_code == 429
    assert person.web.get("/api/photo-lock").json()["blocked_until"]

    # Forgotten code: the reset is confirmed in Telegram.
    assert person.web.post("/api/photo-lock/reset").json() == {"sent": True}
    with sessions() as db:
        message = db.scalars(select(OutboxMessage)).all()[-1]
        assert message.payload["buttons"][0][0]["data"] == "pin:reset"
    assert "сброшен" in person.press("pin:reset")["view"]["text"]
    assert person.web.get("/api/photo-lock").json()["enabled"] is False
    assert picture(person.web.get(url))[0] == "image/jpeg"
    assert "устарел" in person.press("pin:reset")["view"]["text"]


def test_meal_photos_ignore_the_code(person, runner, worker):
    person.web.put("/api/photo-lock", json={"pin": "2468"})
    meal = person.web.post(
        "/api/meals", json={"title": "Суп", "items": [{"name": "Суп", "kcal": 200}]}
    )
    added = person.web.post(
        f"/api/meals/{meal.json()['id']}/photos", files={"photo": ("m.jpg", jpeg(), "image/jpeg")}
    ).json()
    media_id = added["photos"][0]["id"]
    response = person.web.get(f"/api/media/{media_id}?size=original")
    assert picture(response) == ("image/jpeg", (64, 48))
    assert "immutable" in response.headers["cache-control"]


def test_every_two_weeks():
    reminder = Reminder(kind="measure", time="09:00", days=[1], enabled=True, every_weeks=2)
    # Saturday 2026-10-10; the first Monday is the 12th, then every other Monday.
    reminders.reschedule(reminder, "UTC")
    assert reminder.anchor_on is not None
    reminder.anchor_on = date(2026, 10, 12)
    first = reminders.next_run(reminder, "UTC", datetime(2026, 10, 10, 12, 0))
    assert first == datetime(2026, 10, 12, 9, 0)
    second = reminders.next_run(reminder, "UTC", first)
    assert second == datetime(2026, 10, 26, 9, 0)
    assert second - first == timedelta(days=14)
    assert reminders.describe(reminder) == "Сделать замеры: раз в 2 недели, пн в 09:00"


def test_reminder_api_keeps_the_period(person):
    measure = next(r for r in person.web.get("/api/reminders").json() if r["kind"] == "measure")
    assert measure["days"] == [1] and measure["every_weeks"] == 1
    saved = person.web.put(
        f"/api/reminders/{measure['id']}",
        json={"kind": "measure", "time": "09:00", "days": [1], "every_weeks": 2, "enabled": True},
    ).json()
    assert saved["every_weeks"] == 2 and saved["next_run_at"]
    assert "раз в 2 недели" in saved["description"]
