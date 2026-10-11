import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from conftest import BOT_TOKEN, Person, bot_headers, widget_payload
from fastapi.testclient import TestClient


def webapp_init_data(user: dict, auth_date: int | None = None) -> str:
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAH",
        "user": json.dumps(user, separators=(",", ":")),
        "signature": "third-party-signature",
    }
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_widget_login_needs_valid_signature(admin, client):
    forged = widget_payload(1001, "Admin")
    forged["first_name"] = "Mallory"
    assert client.post("/api/auth/telegram", json=forged).status_code == 401
    stale = widget_payload(1001, "Admin", auth_date=int(time.time()) - 3 * 86400)
    stale["auth_date"] = int(time.time()) - 3 * 86400
    assert client.post("/api/auth/telegram", json=stale).status_code == 401
    response = client.post("/api/auth/telegram", json=widget_payload(1001, "Admin"))
    assert response.status_code == 200
    assert "food_session" in response.cookies
    me = client.get("/api/auth/me").json()
    assert me["is_admin"] and me["telegram_id"] == 1001


def test_closed_registration(app, client, invite_link):
    # A stranger without an invite is turned away, by the bot and by the site.
    stranger = TestClient(app, base_url="https://testserver")
    stranger.headers.update(bot_headers(2002))
    view = stranger.post("/api/bot/start", json={"user": {"id": 2002}}).json()["view"]
    assert "приглашению" in view["text"]
    assert client.post("/api/auth/telegram", json=widget_payload(2002)).status_code == 403
    # With the invite link the same person gets in.
    code = invite_link.split("start=")[1]
    view = stranger.post(
        "/api/bot/start", json={"user": {"id": 2002, "first_name": "Даша"}, "payload": code}
    ).json()["view"]
    assert view["text"].startswith("Привет, Даша!")
    assert client.post("/api/auth/telegram", json=widget_payload(2002)).status_code == 200


def test_invite_uses_run_out(app, admin):
    link = admin.web.post("/api/admin/invites", json={"max_uses": 1}).json()["link"]
    code = link.split("start=")[1]
    for telegram_id, expected in ((3001, "Привет"), (3002, "приглашению")):
        bot = TestClient(app, base_url="https://testserver")
        bot.headers.update(bot_headers(telegram_id))
        text = bot.post(
            "/api/bot/start", json={"user": {"id": telegram_id, "first_name": "X"}, "payload": code}
        ).json()["view"]["text"]
        assert expected in text


def test_webapp_login(admin, client):
    data = webapp_init_data({"id": 1001, "first_name": "Admin"})
    response = client.post("/api/auth/webapp", json={"init_data": data})
    assert response.status_code == 200, response.text
    tampered = data.replace("Admin", "Eve")
    assert client.post("/api/auth/webapp", json={"init_data": tampered}).status_code == 401


def test_login_through_the_bot(admin, app):
    browser = TestClient(app, base_url="https://testserver")
    started = browser.post("/api/auth/login-requests", headers={"user-agent": "Firefox"}).json()
    assert started["link"] == f"https://t.me/food_test_bot?start=login_{started['code']}"
    poll = {"code": started["code"], "poll_token": started["poll_token"]}
    assert browser.post("/api/auth/login-requests/poll", json=poll).json() == {"status": "pending"}

    # The person opens the link: the bot asks, they confirm.
    view = admin.bot.post(
        "/api/bot/start",
        json={"user": {"id": 1001, "first_name": "Admin"}, "payload": f"login_{started['code']}"},
    ).json()["view"]
    assert "Firefox" in view["text"]
    assert view["buttons"][0][0]["data"] == f"l:y:{started['code']}"
    assert "подтвержден" in admin.press(f"l:y:{started['code']}")["view"]["text"]

    # Someone who only knows the code (not the poll token) gets nothing.
    other = TestClient(app, base_url="https://testserver")
    wrong = {"code": started["code"], "poll_token": "guess"}
    assert other.post("/api/auth/login-requests/poll", json=wrong).json()["status"] == "expired"

    result = browser.post("/api/auth/login-requests/poll", json=poll).json()
    assert result["status"] == "confirmed" and result["user"]["telegram_id"] == 1001
    assert browser.get("/api/auth/me").status_code == 200
    # A confirmed request signs in only once.
    again = TestClient(app, base_url="https://testserver")
    assert again.post("/api/auth/login-requests/poll", json=poll).json()["status"] == "expired"


def test_rejected_bot_login(admin, app):
    browser = TestClient(app, base_url="https://testserver")
    started = browser.post("/api/auth/login-requests").json()
    admin.press(f"l:n:{started['code']}")
    poll = {"code": started["code"], "poll_token": started["poll_token"]}
    assert browser.post("/api/auth/login-requests/poll", json=poll).json()["status"] == "rejected"
    assert browser.get("/api/auth/me").status_code == 401


def test_logout_and_blocking(admin, make_person):
    person = make_person(4001, "Петя")
    assert person.web.get("/api/auth/me").status_code == 200
    users = admin.web.get("/api/admin/users").json()
    target = next(user for user in users if user["name"] == "Петя")
    admin.web.patch(f"/api/admin/users/{target['id']}", json={"is_blocked": True})
    # Blocking ends the web sessions and closes the bot.
    assert person.web.get("/api/auth/me").status_code == 401
    assert person.say("вес 80.5").status_code == 403
    # Only admins see the admin API.
    assert person.web.get("/api/admin/users").status_code == 401
    other = make_person(4002, "Оля")
    assert other.web.get("/api/admin/users").status_code == 403
    other.web.post("/api/auth/logout")
    assert other.web.get("/api/auth/me").status_code == 401


def test_bot_secret_required(app):
    stranger = TestClient(app, base_url="https://testserver")
    response = stranger.get("/api/bot/outbox", headers={"X-Bot-Secret": "wrong"})
    assert response.status_code == 401


def test_cross_site_writes_refused(admin):
    response = admin.web.post(
        "/api/weights", json={"weight_kg": 80}, headers={"Sec-Fetch-Site": "cross-site"}
    )
    assert response.status_code == 403


def test_person_helper_is_isolated(app):
    # Sanity check of the fixture itself: two people, two cookies.
    first = Person(app, 1001, "Admin")
    assert first.web.get("/api/auth/me").json()["telegram_id"] == 1001


def test_bot_login_by_someone_not_invited_fails_fast(admin, app):
    browser = TestClient(app, base_url="https://testserver")
    started = browser.post("/api/auth/login-requests").json()
    stranger = TestClient(app, base_url="https://testserver")
    stranger.headers.update(bot_headers(9999))
    view = stranger.post(
        "/api/bot/start", json={"user": {"id": 9999}, "payload": f"login_{started['code']}"}
    ).json()["view"]
    assert "приглашению" in view["text"]
    poll = {"code": started["code"], "poll_token": started["poll_token"]}
    # The waiting page learns at once instead of after ten minutes.
    assert browser.post("/api/auth/login-requests/poll", json=poll).json()["status"] == "rejected"
