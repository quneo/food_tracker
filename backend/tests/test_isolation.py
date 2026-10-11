"""One person can never see or change another person's data."""

from conftest import jpeg

MEAL = {
    "title": "Омлет",
    "meal_type": "breakfast",
    "items": [{"name": "Яйца", "grams": 120, "kcal": 170, "protein": 15, "fat": 12, "carbs": 1}],
}


def test_records_are_private(admin, make_person):
    alice = make_person(5001, "Алиса")
    bob = make_person(5002, "Боб")

    meal = alice.web.post("/api/meals", json=MEAL).json()
    alice.web.post(
        f"/api/meals/{meal['id']}/photos", files={"photo": ("m.jpg", jpeg(), "image/jpeg")}
    )
    photo_id = alice.web.get(f"/api/meals/{meal['id']}").json()["photos"][0]["id"]
    weight = alice.web.post("/api/weights", json={"weight_kg": 61.5}).json()
    body = alice.web.post(
        "/api/progress-photos", files={"photo": ("b.jpg", jpeg(), "image/jpeg")}
    ).json()
    fact = alice.web.post("/api/memory", json={"category": "dislike", "text": "Не ест рыбу"}).json()
    reminder = alice.web.get("/api/reminders").json()[0]

    forbidden = [
        ("get", f"/api/meals/{meal['id']}"),
        ("patch", f"/api/meals/{meal['id']}"),
        ("delete", f"/api/meals/{meal['id']}"),
        ("get", f"/api/media/{photo_id}"),
        ("get", f"/api/media/{body['media_id']}?size=original"),
        ("delete", f"/api/weights/{weight['id']}"),
        ("delete", f"/api/progress-photos/{body['id']}"),
        ("delete", f"/api/memory/{fact['id']}"),
        ("delete", f"/api/reminders/{reminder['id']}"),
    ]
    for method, url in forbidden:
        kwargs = {"json": {"title": "x"}} if method == "patch" else {}
        response = getattr(bob.web, method)(url, **kwargs)
        assert response.status_code == 404, (method, url, response.status_code)

    assert bob.web.get("/api/meals?from=2000-01-01&to=2100-01-01").status_code == 400
    today = alice.web.get("/api/today").json()["day"]
    assert bob.web.get(f"/api/meals?from={today}&to={today}").json() == []
    assert bob.web.get("/api/weights").json() == []
    assert bob.web.get("/api/progress-photos").json() == []
    assert bob.web.get("/api/memory").json() == []
    assert all(r["id"] != reminder["id"] for r in bob.web.get("/api/reminders").json())

    # The bot acts only for the Telegram account it names.
    assert bob.press(f"m:dd:{meal['id']}")["toast"] == "Запись уже удалена"
    assert alice.web.get(f"/api/meals/{meal['id']}").status_code == 200

    # Admins manage accounts but cannot open anyone's photos.
    assert admin.web.get(f"/api/media/{photo_id}").status_code == 404
    users = admin.web.get("/api/admin/users").json()
    assert {"meals"} <= set(users[0]) and "memory" not in users[0]


def test_account_deletion_removes_everything(make_person, files):
    person = make_person(6001, "Ира")
    other = make_person(6002, "Оля")
    meal = person.web.post("/api/meals", json=MEAL).json()
    person.web.post(
        f"/api/meals/{meal['id']}/photos", files={"photo": ("m.jpg", jpeg(), "image/jpeg")}
    )
    person.web.post("/api/progress-photos", files={"photo": ("b.jpg", jpeg(), "image/jpeg")})
    other.web.post("/api/progress-photos", files={"photo": ("b.jpg", jpeg(), "image/jpeg")})
    assert len(files.objects) == 6  # original + preview each

    assert (
        person.web.request("DELETE", "/api/auth/account", json={"confirm": "нет"}).status_code
        == 400
    )
    assert (
        person.web.request("DELETE", "/api/auth/account", json={"confirm": "удалить"}).status_code
        == 204
    )
    assert person.web.get("/api/auth/me").status_code == 401
    # Only the other person's files are left.
    assert len(files.objects) == 2
    assert other.web.get("/api/progress-photos").json()
    # The bot no longer knows the deleted person.
    assert person.say("вес 70").status_code == 401
