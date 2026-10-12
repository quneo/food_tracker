from datetime import datetime, timedelta

from sqlalchemy import select

from app.chat.models import OutboxMessage
from app.database import utcnow
from app.reminders import service
from app.reminders.models import Reminder
from app.users.models import User


def test_next_run_respects_time_zone_and_days():
    reminder = Reminder(kind="weight", time="08:00", days=[1, 3], enabled=True)
    # Saturday 2026-10-10 12:00 UTC = 19:00 in Krasnoyarsk (UTC+7).
    after = datetime(2026, 10, 10, 12, 0)
    # Next Monday 08:00 local = Monday 01:00 UTC.
    assert service.next_run(reminder, "Asia/Krasnoyarsk", after) == datetime(2026, 10, 12, 1, 0)
    assert service.next_run(reminder, "Europe/Moscow", after) == datetime(2026, 10, 12, 5, 0)
    reminder.enabled = False
    assert service.next_run(reminder, "Asia/Krasnoyarsk", after) is None


def test_due_reminders_go_to_the_outbox(make_person, sessions):
    person = make_person(8001, "Катя")
    reminders = person.web.get("/api/reminders").json()
    assert {r["kind"] for r in reminders} == {"meal", "weight", "photo", "measure", "review"}
    assert not any(r["enabled"] for r in reminders)
    custom = person.web.post(
        "/api/reminders",
        json={
            "kind": "custom",
            "time": "10:00",
            "days": [1, 2, 3, 4, 5, 6, 7],
            "text": "Пить воду",
        },
    ).json()
    weight = next(r for r in reminders if r["kind"] == "weight")
    person.web.put(
        f"/api/reminders/{weight['id']}",
        json={"kind": "weight", "time": "08:00", "days": [1, 2, 3, 4, 5, 6, 7]},
    )
    person.web.post("/api/weights", json={"weight_kg": 60})  # weighed already today

    with sessions() as db:
        now = utcnow()
        for reminder in db.scalars(select(Reminder).where(Reminder.enabled.is_(True))):
            reminder.next_run_at = now - timedelta(minutes=1)
        stale = db.get(Reminder, custom["id"])
        db.commit()
        sent = service.send_due(db)
        # The weight reminder is skipped (done today), the custom one arrives.
        assert sent == 1
        [message] = db.scalars(select(OutboxMessage)).all()
        assert message.payload["text"] == "⏰ Пить воду"
        assert message.payload["buttons"][0][0]["data"] == f"r:off:{custom['id']}"
        assert stale.next_run_at > now
        # Missed by far (server was down): skipped, not sent late.
        stale.next_run_at = now - timedelta(hours=3)
        db.commit()
        assert service.send_due(db) == 0

    view = person.press(f"r:off:{custom['id']}")["view"]
    assert "Выключено" in view["text"]
    assert not next(r for r in person.web.get("/api/reminders").json() if r["id"] == custom["id"])[
        "enabled"
    ]


def test_blocked_people_get_no_reminders(make_person, sessions):
    person = make_person(8002, "Лена")
    reminder = person.web.post(
        "/api/reminders", json={"kind": "custom", "time": "09:00", "days": [1], "text": "Тест"}
    ).json()
    with sessions() as db:
        db.scalar(select(User).where(User.telegram_id == 8002)).is_blocked = True
        db.get(Reminder, reminder["id"]).next_run_at = utcnow() - timedelta(minutes=1)
        db.commit()
        assert service.send_due(db) == 0
