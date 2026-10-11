"""Day-by-day numbers and period reports.

Days are "empty" (nothing logged), "partial" (probably not everything was logged) or
"complete". Averages use complete days by default, so a forgotten dinner does not make a
week look like a diet. The person can mark any day complete or partial themselves."""

from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.nutrition.models import DayMark, Meal, MealItem
from app.nutrition.service import check_range, targets
from app.progress.models import MEASUREMENTS, Measurement, WeightEntry
from app.users.models import User

FIELDS = ("kcal", "protein", "fat", "carbs")


def _status(meals: int, kcal: float, target: int | None, mark: bool | None) -> str:
    if meals == 0:
        return "empty"
    if mark is not None:
        return "complete" if mark else "partial"
    enough = 0.5 * target if target else 800
    return "complete" if meals >= 2 and kcal >= enough else "partial"


def daily(db: Session, user: User, start: date, end: date) -> list[dict]:
    check_range(start, end)
    meals = db.scalars(
        select(Meal).where(
            Meal.user_id == user.id,
            Meal.status == "confirmed",
            Meal.eaten_on >= start,
            Meal.eaten_on <= end,
        )
    ).all()
    weights = db.scalars(
        select(WeightEntry)
        .where(
            WeightEntry.user_id == user.id,
            WeightEntry.measured_on >= start,
            WeightEntry.measured_on <= end,
        )
        .order_by(WeightEntry.measured_at)
    ).all()
    marks = {
        mark.day: mark.complete
        for mark in db.scalars(
            select(DayMark).where(
                DayMark.user_id == user.id, DayMark.day >= start, DayMark.day <= end
            )
        )
    }
    days: dict[date, dict] = {}
    day = start
    while day <= end:
        days[day] = {"day": day, "meals": 0, **{field: 0.0 for field in FIELDS}, "weight": None}
        day += timedelta(days=1)
    for meal in meals:
        row = days[meal.eaten_on]
        row["meals"] += 1
        for field in FIELDS:
            row[field] += getattr(meal, field)
    for entry in weights:
        days[entry.measured_on]["weight"] = entry.weight_kg  # the day's last weighing
    target = user.profile.kcal_target
    for row in days.values():
        for field in FIELDS:
            row[field] = round(row[field], 1)
        mark = marks.get(row["day"])
        row["status"] = _status(row["meals"], row["kcal"], target, mark)
        row["marked"] = mark is not None
    return list(days.values())


def _average(rows: list[dict], field: str) -> float | None:
    return round(sum(row[field] for row in rows) / len(rows), 1) if rows else None


def report(db: Session, user: User, start: date, end: date, include_partial: bool = False):
    rows = daily(db, user, start, end)
    logged = [row for row in rows if row["status"] != "empty"]
    counted = [row for row in logged if include_partial or row["status"] == "complete"]
    goal = targets(user)
    averages = {field: _average(counted, field) for field in FIELDS}
    kcal_target = goal["kcal"]
    within = (
        sum(abs(row["kcal"] - kcal_target) <= 0.1 * kcal_target for row in counted)
        if kcal_target
        else None
    )
    energy = sum(
        (averages[field] or 0) * factor
        for field, factor in (("protein", 4), ("fat", 9), ("carbs", 4))
    )
    split = (
        {
            field: round((averages[field] or 0) * factor / energy * 100)
            for field, factor in (("protein", 4), ("fat", 9), ("carbs", 4))
        }
        if energy
        else None
    )

    weights = db.scalars(
        select(WeightEntry)
        .where(
            WeightEntry.user_id == user.id,
            WeightEntry.measured_on >= start,
            WeightEntry.measured_on <= end,
        )
        .order_by(WeightEntry.measured_at)
    ).all()
    weight = (
        {
            "first": weights[0].weight_kg,
            "last": weights[-1].weight_kg,
            "change": round(weights[-1].weight_kg - weights[0].weight_kg, 1),
            "min": min(entry.weight_kg for entry in weights),
            "max": max(entry.weight_kg for entry in weights),
            "entries": len(weights),
        }
        if weights
        else None
    )

    changes = []
    entries = db.scalars(
        select(Measurement)
        .where(
            Measurement.user_id == user.id,
            Measurement.measured_on >= start,
            Measurement.measured_on <= end,
        )
        .order_by(Measurement.measured_at)
    ).all()
    for kind, (name, unit) in MEASUREMENTS.items():
        values = [entry.value for entry in entries if entry.kind == kind]
        if values:
            changes.append(
                {
                    "kind": kind,
                    "name": name,
                    "unit": unit,
                    "first": values[0],
                    "last": values[-1],
                    "change": round(values[-1] - values[0], 1),
                }
            )

    names = db.scalars(
        select(MealItem.name)
        .join(Meal)
        .where(
            Meal.user_id == user.id,
            Meal.status == "confirmed",
            Meal.eaten_on >= start,
            Meal.eaten_on <= end,
        )
    ).all()
    foods = Counter(name.strip().lower() for name in names)

    return {
        "start": start,
        "end": end,
        "days": len(rows),
        "logged_days": len(logged),
        "complete_days": sum(row["status"] == "complete" for row in rows),
        "counted_days": len(counted),
        "include_partial": include_partial,
        "averages": averages,
        "targets": goal,
        "days_within_target": within,
        "macro_split": split,
        "weight": weight,
        "measurements": changes,
        "top_foods": [{"name": name, "count": count} for name, count in foods.most_common(8)],
    }


def mark_day(db: Session, user: User, day: date, complete: bool | None):
    mark = db.get(DayMark, (user.id, day))
    if complete is None:
        if mark:
            db.delete(mark)
    elif mark:
        mark.complete = complete
    else:
        db.add(DayMark(user_id=user.id, day=day, complete=complete))
    db.commit()
