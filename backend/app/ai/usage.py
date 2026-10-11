"""How many tokens the assistant spends on a person: Codex's own counts per request."""

from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AiJob
from app.config import Settings
from app.core.timeutil import from_local, local_today, zone
from app.users.models import User

PERIODS = (
    ("today", "Сегодня", 1),
    ("week", "7 дней", 7),
    ("month", "30 дней", 30),
    ("all", "Все время", None),
)


def cost(row: dict, settings: Settings) -> float | None:
    """USD by the configured prices per million tokens; None without prices."""
    if settings.ai_price_input is None or settings.ai_price_output is None:
        return None
    cached_price = settings.ai_price_cached_input
    if cached_price is None:
        cached_price = settings.ai_price_input
    fresh = row["input"] - row["cached"]
    total = (
        fresh * settings.ai_price_input
        + row["cached"] * cached_price
        + row["output"] * settings.ai_price_output
    )
    return round(total / 1_000_000, 4)


def summary(db: Session, user: User, settings: Settings) -> dict:
    tz = zone(user.profile.timezone)
    today = local_today(tz)
    columns = (
        func.count(AiJob.id),
        # Requests answered before the runner reported tokens have none.
        func.count(AiJob.input_tokens),
        func.coalesce(func.sum(AiJob.input_tokens), 0),
        func.coalesce(func.sum(AiJob.cached_input_tokens), 0),
        func.coalesce(func.sum(AiJob.output_tokens), 0),
        func.coalesce(func.sum(AiJob.reasoning_output_tokens), 0),
    )
    done = (AiJob.user_id == user.id, AiJob.status == "done")
    periods = []
    for key, label, days in PERIODS:
        query = select(*columns).where(*done)
        if days:
            start = datetime.combine(today - timedelta(days=days - 1), time())
            query = query.where(AiJob.finished_at >= from_local(start, tz))
        requests, measured, input_, cached, output, reasoning = db.execute(query).one()
        row = {
            "key": key,
            "label": label,
            "requests": requests,
            "measured": measured,
            "input": input_,
            "cached": cached,
            "output": output,
            "reasoning": reasoning,
            "total": input_ + output,
        }
        row["cost"] = cost(row, settings)
        periods.append(row)
    model = db.scalar(
        select(AiJob.model)
        .where(*done, AiJob.model.is_not(None))
        .order_by(AiJob.id.desc())
        .limit(1)
    )
    return {
        "periods": periods,
        "model": model,
        "priced": periods[0]["cost"] is not None,
    }
