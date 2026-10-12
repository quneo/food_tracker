"""Message -> job -> Codex (fake) -> validated actions -> records and outbox."""

import asyncio

import pytest
from conftest import jpeg
from sqlalchemy import select

from app.ai.runner import RunnerError
from app.ai.schemas import TurnResult
from app.ai.strict_schema import strict_schema
from app.chat.models import OutboxMessage


def item(name, grams, kcal, protein=0, fat=0, carbs=0, source="estimated"):
    return {
        "name": name,
        "product_id": None,
        "grams": grams,
        "grams_source": source,
        "kcal": kcal,
        "protein": protein,
        "fat": fat,
        "carbs": carbs,
        "confidence": "medium",
        "note": None,
    }


def estimate(title, items, low=None, high=None):
    total = sum(entry["kcal"] for entry in items)
    return {
        "title": title,
        "meal_type": "lunch",
        "eaten_at": None,
        "items": items,
        "kcal_low": low or total * 0.8,
        "kcal_high": high or total * 1.3,
        "confidence": "medium",
        "assumptions": ["Масло при жарке ~10 г"],
        "comment": None,
    }


LUNCH = estimate(
    "Курица с рисом",
    [
        item("Куриная грудка жареная", 150, 250, 45, 6, 0),
        item("Рис отварной", 180, 230, 4, 1, 50),
        item("Масло подсолнечное", 10, 90, 0, 10, 0),
    ],
)


def run_jobs(worker):
    asyncio.run(worker.drain())


def outbox(sessions):
    with sessions() as db:
        return db.scalars(select(OutboxMessage).order_by(OutboxMessage.id)).all()


@pytest.fixture
def person(make_person):
    person = make_person(7001, "Вадим")
    person.start_session()  # the assistant only hears messages inside a session
    return person


def test_photo_becomes_a_draft_and_is_saved(person, runner, worker, sessions):
    runner.answers.append(
        {
            "reply": "Выглядит сытно! Риса около полной порции.",
            "actions": [
                {"kind": "create_meal", "meal": LUNCH, "use_photos": True},
                {"kind": "remember", "category": "habit", "text": "Обедает около 13:00"},
            ],
        }
    )
    response = person.say("обед", photos=[jpeg()], status_message_id=77).json()
    assert response["job_id"] and response["view"] is None
    run_jobs(worker)

    call = runner.calls[0]
    assert len(call["images"]) == 1 and call["images"][0][:3] == b"\xff\xd8\xff"
    assert "## Новое сообщение пользователя" in call["prompt"]
    assert "обед" in call["prompt"] and "Фото 1: новое" in call["prompt"]
    assert call["schema"] == strict_schema(TurnResult)

    [message] = outbox(sessions)
    payload = message.payload
    # The answer replaces the bot's "thinking…" message and carries the meal card.
    assert payload["edit_message_id"] == 77 and message.chat_id == 7001
    assert "Курица с рисом" in payload["text"] and "≈ 570 ккал" in payload["text"]
    assert "~150 г" in payload["text"]  # a guessed weight is shown as a guess
    assert "📝 Запомнил: Обедает около 13:00" in payload["text"]
    buttons = [button["data"] for row in payload["buttons"] for button in row if "data" in button]
    meal_id = int(buttons[0].split(":")[2])
    assert buttons[0] == f"m:ok:{meal_id}"

    meal = person.web.get(f"/api/meals/{meal_id}").json()
    assert meal["status"] == "draft" and meal["estimated_by"] == "ai"
    assert len(meal["photos"]) == 1 and meal["kcal"] == 570
    assert meal["items"][0]["grams_source"] == "estimated"
    assert person.web.get("/api/today").json()["totals"]["kcal"] == 0  # drafts do not count

    view = person.press(f"m:ok:{meal_id}")["view"]
    assert "сохранено ✅" in view["text"]
    assert person.web.get("/api/today").json()["totals"]["kcal"] == 570
    assert [fact["text"] for fact in person.web.get("/api/memory").json()] == [
        "Обедает около 13:00"
    ]


def test_fix_button_edits_the_meal_directly(person, runner, worker):
    runner.answers.append(
        {"reply": "", "actions": [{"kind": "create_meal", "meal": LUNCH, "use_photos": False}]}
    )
    person.say("курица с рисом")
    run_jobs(worker)
    meal = person.web.get("/api/today").json()["meals"][0]
    person.press(f"m:ok:{meal['id']}")

    # "Fix" on a saved meal: the next message corrects it without another question.
    message = person.press(f"m:e:{meal['id']}")["message"]
    assert "Что исправить" in message["text"]
    fixed = estimate("Курица с рисом", [item("Куриная грудка", 150, 250), item("Рис", 250, 320)])
    runner.answers.append(
        {
            "reply": "Исправил.",
            "actions": [{"kind": "update_meal", "meal_id": meal["id"], "meal": fixed}],
        }
    )
    person.say("риса было 250 г, без масла")
    run_jobs(worker)
    assert f"[meal {meal['id']}]" in runner.calls[1]["prompt"]
    assert "нажал «Исправить»" in runner.calls[1]["prompt"]
    updated = person.web.get(f"/api/meals/{meal['id']}").json()
    assert updated["kcal"] == 570 and len(updated["items"]) == 2
    assert updated["status"] == "confirmed"


def test_changes_to_saved_records_wait_for_yes(person, runner, worker, sessions):
    meal = person.web.post(
        "/api/meals",
        json={"title": "Ужин", "items": [{"name": "Паста", "grams": 300, "kcal": 600}]},
    ).json()
    runner.answers.append(
        {
            "reply": "Удалить ужин?",
            "actions": [
                {"kind": "delete_meal", "meal_id": meal["id"]},
                {"kind": "delete_meal", "meal_id": 99999},  # not theirs / not existing
            ],
        }
    )
    person.say("удали ужин")
    run_jobs(worker)
    messages = outbox(sessions)
    assert "не нашел прием пищи #99999" in messages[0].payload["text"]
    confirm = messages[0].payload["buttons"][0][0]["data"]
    assert confirm.startswith("a:y:")
    # Nothing is deleted until the person says yes.
    assert person.web.get(f"/api/meals/{meal['id']}").status_code == 200
    assert "Удалено" in person.press(confirm)["view"]["text"]
    assert person.web.get(f"/api/meals/{meal['id']}").status_code == 404
    # A second press does nothing.
    assert person.press(confirm)["toast"] == "Уже выполнено или устарело"


def test_other_peoples_ids_are_rejected(person, make_person, runner, worker, sessions):
    other = make_person(7002, "Чужой")
    meal = other.web.post(
        "/api/meals", json={"title": "Чужой обед", "items": [{"name": "Суп", "kcal": 200}]}
    ).json()
    runner.answers.append(
        {
            "reply": "Готово",
            "actions": [{"kind": "update_meal", "meal_id": meal["id"], "meal": LUNCH}],
        }
    )
    person.say("исправь обед")
    run_jobs(worker)
    assert "Не получилось" in outbox(sessions)[0].payload["text"]
    assert other.web.get(f"/api/meals/{meal['id']}").json()["title"] == "Чужой обед"


def test_body_and_settings_actions(person, runner, worker, sessions):
    runner.answers.append(
        {
            "reply": "Записал.",
            "actions": [
                {"kind": "log_weight", "weight_kg": 82.4, "measured_at": None},
                {
                    "kind": "log_measurements",
                    "values": [{"kind": "waist", "value": 84}, {"kind": "body_fat", "value": 18}],
                    "measured_at": None,
                },
                {
                    "kind": "set_reminder",
                    "reminder_kind": "weight",
                    "time": "07:30",
                    "days": [1, 2, 3, 4, 5],
                    "every_weeks": None,
                    "text": None,
                },
                {
                    "kind": "update_profile",
                    "changes": {
                        "sex": "male",
                        "birth_date": "1992-05-01",
                        "height_cm": 181,
                        "activity": None,
                        "goal": "lose",
                        "target_weight_kg": 78,
                        "kcal_target": 900,  # below the safe floor: refused
                        "protein_target": None,
                        "fat_target": None,
                        "carbs_target": None,
                        "timezone": None,
                    },
                },
            ],
        }
    )
    person.say("вешу 82.4, талия 84, жир 18%. напоминай взвешиваться по будням в 7:30")
    run_jobs(worker)
    text = outbox(sessions)[0].payload["text"]
    assert "⚖️ Записал вес: 82,4 кг" in text
    assert "талия 84 см" in text and "процент жира 18 %" in text
    assert "Взвеситься: по будням в 07:30" in text
    # The whole profile change is refused because one value is unsafe.
    assert "ккал: значение вне диапазона" in text
    assert person.web.get("/api/profile").json()["height_cm"] is None
    reminders = person.web.get("/api/reminders").json()
    weight = next(r for r in reminders if r["kind"] == "weight")
    assert weight["enabled"] and weight["time"] == "07:30" and weight["next_run_at"]

    undo = outbox(sessions)[0].payload["buttons"][-1][0]
    assert undo["text"] == "↩️ Отменить"
    view = person.press(undo["data"])["view"]
    # The message stays readable, the undo button goes away.
    assert view["text"].startswith("Записал.") and view["text"].endswith("↩️ Отменено")
    assert view["buttons"] == []
    assert person.web.get("/api/weights").json() == []
    assert person.web.get("/api/measurements").json() == []


def test_fast_paths_skip_the_assistant(person, runner, worker):
    view = person.say("вес 81,7").json()["view"]
    assert view["text"].startswith("⚖️ Записал вес: 81,7 кг")
    assert person.say("Прогресс, спереди", photos=[jpeg()]).json()["view"]["text"].startswith("📸")
    photos = person.web.get("/api/progress-photos").json()
    assert photos[0]["note"] == "спереди" and photos[0]["weight_kg"] == 81.7
    # A bare number is not a weight: it goes to the assistant.
    runner.answers.append({"reply": "Это вес или калории?", "actions": []})
    assert person.say("82").json()["job_id"]
    run_jobs(worker)
    assert runner.calls and not runner.answers


def test_progress_mode_covers_one_photo(person, runner, worker):
    view = person.bot.post("/api/bot/progress-mode").json()["view"]
    assert view["buttons"][0][0]["data"] == "p:x"
    assert person.say(photos=[jpeg(), jpeg()]).json()["view"]["text"].startswith("📸")
    # The next photo is food again: it goes to the assistant, not to the album.
    runner.answers.append({"reply": "Похоже на салат", "actions": []})
    assert person.say(photos=[jpeg()]).json()["job_id"]
    run_jobs(worker)
    assert len(person.web.get("/api/progress-photos").json()) == 2
    # Cancelled, or followed by a text message: no body photo either.
    person.bot.post("/api/bot/progress-mode")
    assert "отменил" in person.press("p:x")["view"]["text"]
    runner.answers.append({"reply": "Ок", "actions": []})
    assert person.say(photos=[jpeg()]).json()["job_id"]
    run_jobs(worker)
    assert len(person.web.get("/api/progress-photos").json()) == 2


def test_runner_failures(person, runner, worker, sessions):
    runner.answers += [
        RunnerError("ssh", "connection reset", transient=True),
        RunnerError("timeout", "slow", transient=True),
    ]
    person.say("что поесть?", status_message_id=9)
    run_jobs(worker)
    # One retry, then the person gets a clear message in place of "thinking…".
    assert len(runner.calls) == 2
    [message] = outbox(sessions)
    assert message.payload["edit_message_id"] == 9
    assert "слишком долго" in message.payload["text"]


def test_invalid_answer_is_not_applied(person, runner, worker, sessions):
    runner.answers += [{"reply": "ok", "actions": [{"kind": "drop_database"}]}] * 2
    person.say("привет")
    run_jobs(worker)
    assert "непонятное" in outbox(sessions)[0].payload["text"]


def test_outbox_delivery_report(person, runner, worker, sessions):
    runner.answers.append({"reply": "Привет!", "actions": []})
    person.say("привет")
    run_jobs(worker)
    pending = person.bot.get("/api/bot/outbox").json()
    assert pending[0]["text"] == "Привет!" and pending[0]["chat_id"] == 7001
    person.bot.post(f"/api/bot/outbox/{pending[0]['id']}", json={"message_id": 555})
    assert person.bot.get("/api/bot/outbox").json() == []


def test_conversation_and_memory_reach_the_prompt(person, runner, worker):
    person.web.post("/api/memory", json={"category": "allergy", "text": "Аллергия на арахис"})
    runner.answers += [{"reply": "Понял", "actions": []}, {"reply": "Ок", "actions": []}]
    person.say("я сегодня тренировался")
    run_jobs(worker)
    person.say("что съесть после тренировки?")
    run_jobs(worker)
    prompt = runner.calls[1]["prompt"]
    assert "(allergy) Аллергия на арахис" in prompt
    assert "Пользователь: я сегодня тренировался" in prompt
    assert "Ассистент: Понял" in prompt
    # /new starts over: earlier messages leave the prompt, memory stays.
    person.bot.post("/api/bot/new")
    runner.answers.append({"reply": "Ок", "actions": []})
    person.say("а теперь?")
    run_jobs(worker)
    assert "тренировался" not in runner.calls[2]["prompt"]
    assert "Аллергия на арахис" in runner.calls[2]["prompt"]
