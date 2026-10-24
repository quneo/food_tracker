"""Token usage in the profile; what the assistant sees about the person."""

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.ai import usage
from app.ai.models import AiJob
from app.database import utcnow

REPLY = {"reply": "Привет!", "actions": []}


@pytest.fixture
def person(make_person):
    person = make_person(9201, "Вадим")
    person.start_session()  # the assistant only hears messages inside a session
    return person


def test_token_usage_by_period(person, runner, worker, sessions):
    runner.answers.append(REPLY)
    person.say("привет")
    asyncio.run(worker.drain())
    with sessions() as db:
        job = db.scalar(select(AiJob))
        assert (job.input_tokens, job.cached_input_tokens) == (1000, 800)
        assert (job.output_tokens, job.reasoning_output_tokens) == (200, 50)
        # A request from 40 days ago, answered before the runner reported tokens.
        old = AiJob(
            user_id=job.user_id,
            message_id=job.message_id,
            status="done",
            finished_at=utcnow() - timedelta(days=40),
        )
        db.add(old)
        db.commit()

    data = person.web.get("/api/profile/ai-usage").json()
    periods = {row["key"]: row for row in data["periods"]}
    assert periods["today"] == {
        "key": "today",
        "label": "Сегодня",
        "requests": 1,
        "measured": 1,
        "input": 1000,
        "cached": 800,
        "output": 200,
        "reasoning": 50,
        "total": 1200,
        "cost": None,
    }
    assert periods["month"]["requests"] == 1
    assert periods["all"]["requests"] == 2 and periods["all"]["measured"] == 1
    assert data["model"] == "gpt-test" and data["priced"] is False


def test_cost_by_configured_prices():
    row = {"input": 1_000_000, "cached": 600_000, "output": 100_000}
    prices = SimpleNamespace(ai_price_input=2.0, ai_price_cached_input=0.5, ai_price_output=8.0)
    # 400k fresh * 2 + 600k cached * 0.5 + 100k * 8 per million
    assert usage.cost(row, prices) == 1.9
    prices.ai_price_cached_input = None
    assert usage.cost(row, prices) == 2.8
    prices.ai_price_output = None
    assert usage.cost(row, prices) is None


def test_context_knows_targets_body_and_the_week(person, runner, worker):
    person.web.put(
        "/api/profile",
        json={
            "sex": "male",
            "birth_date": "1995-05-01",
            "height_cm": 180,
            "activity": "moderate",
            "goal": "lose",
            "target_weight_kg": 78,
            "kcal_target": 2100,
            "protein_target": 150,
            "fat_target": 70,
            "carbs_target": 210,
            "timezone": "Europe/Moscow",
        },
    )
    person.web.post("/api/weights", json={"weight_kg": 84.5})
    person.web.post(
        "/api/meals",
        json={"title": "Омлет", "items": [{"name": "Омлет", "kcal": 400, "protein": 30}]},
    )
    today = date.fromisoformat(person.web.get("/api/today").json()["day"])
    person.web.post(
        "/api/meals",
        json={
            "title": "Гречка с котлетой",
            "eaten_at": f"{today - timedelta(days=1)}T13:10",
            "items": [{"name": "Гречка", "kcal": 520}],
        },
    )
    runner.answers.append(REPLY)
    person.say("что посоветуешь на ужин?")
    asyncio.run(worker.drain())
    prompt = runner.calls[-1]["prompt"]
    assert "Норма в день: ккал 2100, Б 150, Ж 70, У 210" in prompt
    assert "До нормы осталось: ккал 1700, Б 120" in prompt
    assert "ИМТ: 26.1" in prompt
    assert "Расчет по Миффлину" in prompt
    assert "приходят черновиком" in prompt
    assert "## Статистика за 7 дн." in prompt
    # Earlier days show what was eaten, not only the totals.
    assert "  ели: 13:10 Гречка с котлетой 520" in prompt
