"""Saved products (label numbers), the assistant's meal comments, diet reviews."""

import asyncio
from datetime import timedelta

import pytest
from conftest import jpeg
from sqlalchemy import select

from app.ai.models import AiJob
from app.chat.models import OutboxMessage
from app.database import utcnow
from app.reminders import service as reminders
from app.reminders.models import Reminder

MILK = {
    "name": "Молоко Простоквашино 2,5%",
    "brand": "Простоквашино",
    "kcal": 53,
    "protein": 2.9,
    "fat": 2.5,
    "carbs": 4.7,
    "portion_name": "стакан",
    "portion_grams": 250,
    "package_grams": 930,
    "comment": None,
}


def run_jobs(worker):
    asyncio.run(worker.drain())


def outbox(sessions):
    with sessions() as db:
        return db.scalars(select(OutboxMessage).order_by(OutboxMessage.id)).all()


@pytest.fixture
def person(make_person):
    person = make_person(9101, "Вадим")
    person.start_session()  # the assistant only hears messages inside a session
    return person


def test_products_on_the_site(person, make_person, files):
    created = person.web.post("/api/products", json=MILK).json()
    assert created["kcal"] == 53 and created["photos"] == []
    assert person.web.post("/api/products", json=MILK).status_code == 409  # same name
    with_photo = person.web.post(
        f"/api/products/{created['id']}/photos", files={"photo": ("l.jpg", jpeg(), "image/jpeg")}
    ).json()
    assert len(with_photo["photos"]) == 1
    patched = person.web.patch(f"/api/products/{created['id']}", json={"fat": 3.2}).json()
    assert patched["fat"] == 3.2 and patched["kcal"] == 53
    assert [p["name"] for p in person.web.get("/api/products?q=молоко").json()] == [MILK["name"]]

    # Someone else sees nothing and cannot link the product to their meals.
    other = make_person(9102, "Чужой")
    assert other.web.get(f"/api/products/{created['id']}").status_code == 404
    assert other.web.get("/api/products").json() == []
    meal = other.web.post(
        "/api/meals",
        json={
            "title": "Молоко",
            "items": [{"name": "Молоко", "product_id": created["id"], "grams": 200, "kcal": 100}],
        },
    ).json()
    assert meal["items"][0]["product_id"] is None

    assert person.web.delete(f"/api/products/{created['id']}").status_code == 204
    assert files.objects == {}


def test_assistant_saves_a_product_from_a_label(person, runner, worker, sessions):
    runner.answers.append(
        {
            "reply": "",
            "actions": [{"kind": "save_product", "product_id": None, "use_photos": True, **MILK}],
        }
    )
    person.say("запомни мое молоко", photos=[jpeg(), jpeg()])
    run_jobs(worker)
    text = outbox(sessions)[0].payload["text"]
    assert "🏷 Сохранил продукт «Молоко Простоквашино 2,5%»: 53 ккал" in text
    [product] = person.web.get("/api/products").json()
    assert len(product["photos"]) == 2 and product["portion_grams"] == 250

    # Next time the product is in the prompt and the app computes the numbers itself.
    runner.answers.append(
        {
            "reply": "",
            "actions": [
                {
                    "kind": "create_meal",
                    "use_photos": False,
                    "meal": {
                        "title": "Молоко",
                        "meal_type": "snack",
                        "eaten_at": None,
                        "items": [
                            {
                                "name": "Молоко 2,5%",
                                "product_id": product["id"],
                                "grams": 250,
                                "grams_source": "stated",
                                "kcal": 999,  # the model's guess is ignored
                                "protein": 0,
                                "fat": 0,
                                "carbs": 0,
                                "confidence": "high",
                                "note": None,
                            }
                        ],
                        "kcal_low": 120,
                        "kcal_high": 140,
                        "confidence": "high",
                        "assumptions": [],
                        "comment": "Хороший перекус: 7 г белка без сахара сверху.",
                    },
                }
            ],
        }
    )
    person.say("выпил стакан моего молока")
    run_jobs(worker)
    assert f"[product {product['id']}] Молоко Простоквашино 2,5%" in runner.calls[1]["prompt"]
    meal = person.web.get("/api/today").json()["meals"][0]
    assert meal["kcal"] == 132.5 and meal["protein"] == 7.2
    assert meal["items"][0]["product_id"] == product["id"]
    assert meal["ai_comment"] == "Хороший перекус: 7 г белка без сахара сверху."
    card = outbox(sessions)[-1].payload["text"]
    assert "💬 <i>Хороший перекус" in card
    assert person.web.get(f"/api/products/{product['id']}").json()["uses"] == 1


def test_review_from_the_menu(person, runner, worker, sessions):
    person.web.post(
        "/api/meals",
        json={"title": "Обед", "items": [{"name": "Суп", "grams": 300, "kcal": 250}]},
    )
    menu = person.bot.get("/api/bot/review").json()["view"]
    assert [button["data"] for button in menu["buttons"][0]] == ["rv:1", "rv:7", "rv:14", "rv:30"]
    pressed = person.bot.post("/api/bot/press", json={"data": "rv:7", "message_id": 321}).json()
    assert pressed["job_id"] and "Разбираю рацион за неделю" in pressed["view"]["text"]

    runner.answers.append({"reply": "**Что хорошо**\n• Супы на обед", "actions": []})
    run_jobs(worker)
    prompt = runner.calls[0]["prompt"]
    assert "# Task: a review of the diet" in prompt
    assert "## Статистика за 7 дн." in prompt and "Дней с записями 1 из 7" in prompt
    # The menu says "reviewing…"; the review itself comes as a new message.
    [message] = outbox(sessions)
    assert "edit_message_id" not in message.payload
    assert message.payload["text"].startswith("<b>Что хорошо</b>")


def test_weekly_review_reminder_starts_a_job(person, sessions):
    with sessions() as db:
        reminder = db.scalar(select(Reminder).where(Reminder.kind == "review"))
        reminder.enabled = True
        reminder.next_run_at = utcnow() - timedelta(minutes=1)
        db.commit()
        assert reminders.send_due(db) == 1
        job = db.scalar(select(AiJob))
        assert job.kind == "review" and job.days == 7
        # The review opens a session (this person had none), so questions can follow.
        [message] = db.scalars(select(OutboxMessage)).all()
        assert message.payload["text"].startswith("🟢 <b>Сессия началась</b>")
        assert message.payload["keyboard"][0][0] == "⏹ Завершить сессию"
