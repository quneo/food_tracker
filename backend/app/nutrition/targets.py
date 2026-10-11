"""Suggested daily targets: Mifflin-St Jeor energy needs, activity factor, goal adjustment.

A starting point to adjust by the weight trend, not a prescription."""

from datetime import date

ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "high": 1.725, "very_high": 1.9}
GOAL = {"lose": 0.85, "maintain": 1.0, "gain": 1.1}
# Grams of protein per kg of body weight.
PROTEIN = {"lose": 1.8, "maintain": 1.6, "gain": 1.8}
MIN_KCAL = {"male": 1500, "female": 1200}


def age(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def suggest(
    sex: str | None,
    birth_date: date | None,
    height_cm: float | None,
    weight_kg: float | None,
    activity: str | None,
    goal: str | None,
    today: date,
) -> dict | None:
    """-> {"kcal", "protein", "fat", "carbs", "bmr", "tdee"}, or None if data is missing."""
    if not (sex and birth_date and height_cm and weight_kg):
        return None
    years = age(birth_date, today)
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * years + (5 if sex == "male" else -161)
    tdee = bmr * ACTIVITY.get(activity or "light", 1.375)
    goal = goal or "maintain"
    kcal = max(tdee * GOAL[goal], MIN_KCAL[sex])
    # Deficit no deeper than 750 kcal a day.
    if goal == "lose":
        kcal = max(kcal, tdee - 750)
    protein = PROTEIN[goal] * weight_kg
    fat = max(0.8 * weight_kg, kcal * 0.25 / 9)
    carbs = max((kcal - protein * 4 - fat * 9) / 4, 0)
    return {
        "kcal": round(kcal / 10) * 10,
        "protein": round(protein),
        "fat": round(fat),
        "carbs": round(carbs),
        "bmr": round(bmr),
        "tdee": round(tdee),
    }
