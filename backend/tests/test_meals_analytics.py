from datetime import date, timedelta

import pytest
from conftest import jpeg

from app.ai.schemas import TurnResult
from app.ai.strict_schema import strict_schema
from app.nutrition.targets import suggest


def meal(title, kcal, eaten_at=None, protein=10, fat=10, carbs=10, meal_type=None):
    body = {
        "title": title,
        "items": [
            {
                "name": title,
                "grams": 200,
                "kcal": kcal,
                "protein": protein,
                "fat": fat,
                "carbs": carbs,
            }
        ],
    }
    if eaten_at:
        body["eaten_at"] = eaten_at
    if meal_type:
        body["meal_type"] = meal_type
    return body


@pytest.fixture
def person(make_person):
    return make_person(9001, "Таня")


def test_manual_meal_edit_and_photos(person, files):
    created = person.web.post("/api/meals", json=meal("Каша", 300)).json()
    assert created["status"] == "confirmed" and created["estimated_by"] == "user"
    assert created["items"][0]["grams_source"] == "stated"
    patched = person.web.patch(
        f"/api/meals/{created['id']}",
        json={
            "meal_type": "breakfast",
            "items": [
                {"name": "Овсянка", "grams": 250, "kcal": 280, "protein": 9, "fat": 6, "carbs": 45},
                {"name": "Банан", "grams": 120, "kcal": 105, "carbs": 27},
            ],
        },
    ).json()
    assert patched["kcal"] == 385 and patched["carbs"] == 72 and patched["meal_type"] == "breakfast"

    with_photo = person.web.post(
        f"/api/meals/{created['id']}/photos", files={"photo": ("p.jpg", jpeg(), "image/jpeg")}
    ).json()
    photo = with_photo["photos"][0]
    preview = person.web.get(f"/api/media/{photo['id']}")
    assert preview.headers["content-type"] == "image/webp"
    assert preview.headers["cache-control"].startswith("private")
    original = person.web.get(f"/api/media/{photo['id']}?size=original")
    assert original.content == jpeg()
    bad = person.web.post(
        f"/api/meals/{created['id']}/photos",
        files={"photo": ("x.jpg", b"not an image", "image/jpeg")},
    )
    assert bad.status_code == 400

    assert person.web.delete(f"/api/meals/{created['id']}").status_code == 204
    assert files.objects == {}  # original and preview deleted from storage


def test_future_time_is_refused(person):
    later = (date.today() + timedelta(days=2)).isoformat() + "T12:00"
    assert person.web.post("/api/meals", json=meal("Суп", 200, later)).status_code == 400


def test_daily_statuses_and_report(person):
    today = date.fromisoformat(person.web.get("/api/today").json()["day"])
    person.web.put("/api/profile", json={"timezone": "Asia/Krasnoyarsk", "kcal_target": 2000})
    two_days_ago = today - timedelta(days=2)
    yesterday = today - timedelta(days=1)
    for title, kcal, day in [
        ("Завтрак", 600, two_days_ago),
        ("Обед", 900, two_days_ago),
        ("Ужин", 500, two_days_ago),
        ("Перекус", 300, yesterday),  # one small meal: probably not everything logged
    ]:
        person.web.post("/api/meals", json=meal(title, kcal, f"{day}T12:00"))
    person.web.post(
        "/api/weights", json={"weight_kg": 70.0, "measured_at": f"{two_days_ago}T08:00"}
    )
    person.web.post("/api/weights", json={"weight_kg": 69.4, "measured_at": f"{yesterday}T08:00"})

    start = (today - timedelta(days=3)).isoformat()
    days = person.web.get(f"/api/analytics/daily?from={start}&to={today}").json()
    status = {row["day"]: row["status"] for row in days}
    assert status[str(two_days_ago)] == "complete"
    assert status[str(yesterday)] == "partial"
    assert status[str(today)] == "empty"

    report = person.web.get(f"/api/analytics/report?from={start}&to={today}").json()
    assert report["logged_days"] == 2 and report["counted_days"] == 1
    assert report["averages"]["kcal"] == 2000 and report["days_within_target"] == 1
    assert report["weight"]["change"] == -0.6
    with_partial = person.web.get(
        f"/api/analytics/report?from={start}&to={today}&include_partial=true"
    ).json()
    assert with_partial["averages"]["kcal"] == 1150

    # The person says yesterday was complete after all.
    person.web.put(f"/api/analytics/days/{yesterday}", json={"complete": True})
    report = person.web.get(f"/api/analytics/report?from={start}&to={today}").json()
    assert report["counted_days"] == 2


def test_suggested_targets(person):
    assert person.web.get("/api/profile/suggested-targets").status_code == 400
    person.web.put(
        "/api/profile",
        json={
            "timezone": "Europe/Moscow",
            "sex": "female",
            "birth_date": "1995-03-10",
            "height_cm": 168,
            "activity": "moderate",
            "goal": "lose",
        },
    )
    person.web.post("/api/weights", json={"weight_kg": 70})
    targets = person.web.get("/api/profile/suggested-targets").json()
    assert 1500 <= targets["kcal"] <= 2000 and targets["protein"] == 126


def test_targets_never_below_floor():
    result = suggest("female", date(1990, 1, 1), 150, 45, "sedentary", "lose", date(2026, 10, 1))
    assert result["kcal"] >= 1200


def test_output_schema_is_strict():
    schema = strict_schema(TurnResult)
    text = str(schema)
    for word in ("oneOf", "const", "$ref", "$defs", "default", "discriminator"):
        assert f"'{word}'" not in text

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    kinds = schema["properties"]["actions"]["items"]["anyOf"]
    assert len(kinds) == 14


def test_measurement_edit_keeps_its_id(person):
    entry = person.web.post("/api/measurements", json={"kind": "waist", "value": 82}).json()
    edited = person.web.put(
        f"/api/measurements/{entry['id']}", json={"kind": "waist", "value": 81.5}
    ).json()
    assert edited["id"] == entry["id"] and edited["value"] == 81.5
    assert edited["measured_at"] == entry["measured_at"]
