"""REGISTRATION=bastion: sign-in on the site through Bastion, Telegram linked afterwards."""

import pytest
from conftest import bot_headers
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.bastion import BastionError, BastionUnavailable
from app.users import service as users

CODE = "123456"
ACCOUNTS = {
    "vadim": {"id": "b-vadim", "password": "pw-vadim", "display_name": "Вадим"},
    "daria": {"id": "b-daria", "password": "pw-daria", "display_name": "Даша"},
}


class FakeBastion:
    allowed = {"b-vadim", "b-daria"}
    down = False

    def __init__(self, *args, **kwargs):
        pass

    def authenticate(self, username, password, totp_code, end_user_ip=None):
        if self.down:
            raise BastionUnavailable("connection refused")
        account = ACCOUNTS.get(username)
        if not account or account["password"] != password:
            raise BastionError(401, "invalid_credentials")
        if not totp_code:
            raise BastionError(401, "totp_required")
        if totp_code != CODE:
            raise BastionError(401, "invalid_totp")
        if account["id"] not in self.allowed:
            raise BastionError(403, "access_denied")
        return {
            "id": account["id"],
            "username": username,
            "display_name": account["display_name"],
            "groups": ["family"],
            "is_active": True,
        }

    def users(self):
        return [{"id": user_id} for user_id in self.allowed]


@pytest.fixture
def bastion(monkeypatch):
    settings = get_settings()
    for name, value in {
        "registration": "bastion",
        "bastion_url": "http://bastion.test",
        "bastion_client_id": "food-test",
        "bastion_client_secret": "secret",
        "admin_usernames": "vadim",
    }.items():
        monkeypatch.setattr(settings, name, value)
    FakeBastion.allowed = {"b-vadim", "b-daria"}
    FakeBastion.down = False
    monkeypatch.setattr(users, "BastionClient", FakeBastion)
    return FakeBastion


def browser(app):
    return TestClient(app, base_url="https://testserver")


def sign_in(client, username="vadim", password=None, code=CODE):
    password = password or ACCOUNTS.get(username, {}).get("password", "x")
    return client.post(
        "/api/auth/bastion", json={"username": username, "password": password, "totp_code": code}
    )


def test_sign_in_with_bastion(app, bastion):
    client = browser(app)
    assert client.get("/api/auth/config").json()["bastion"] is True
    assert sign_in(client, password="wrong").json()["detail"] == "Неверный логин или пароль."
    assert sign_in(client, code=None).json()["code"] == "totp_required"
    assert sign_in(client, code="000000").status_code == 401
    response = sign_in(client, code="123 456")
    assert response.status_code == 200, response.text
    me = client.get("/api/auth/me").json()
    assert me["name"] == "Вадим" and me["login"] == "vadim" and me["bastion"]
    assert me["telegram_id"] is None and me["is_admin"]
    # A second sign-in finds the same account.
    other = browser(app)
    sign_in(other)
    assert other.get("/api/auth/me").json()["id"] == me["id"]

    bastion.down = True
    assert sign_in(browser(app)).status_code == 503


def test_bastion_decides_who_gets_in(app, bastion):
    bastion.allowed = {"b-vadim"}
    response = sign_in(browser(app), "daria")
    assert response.status_code == 403 and response.json()["code"] == "access_denied"


def test_link_telegram_through_the_bot(app, bastion, sessions):
    web = browser(app)
    sign_in(web)
    bot = browser(app)
    bot.headers.update(bot_headers(7777))

    # Before linking, the bot does not know this Telegram account.
    view = bot.post("/api/bot/start", json={"user": {"id": 7777, "first_name": "Vadim"}}).json()
    assert "Bastion" in view["view"]["text"]
    assert bot.post("/api/bot/messages", data={"text": "вес 80"}).status_code == 401

    link = web.post("/api/auth/telegram-link").json()["link"]
    code = link.split("start=link_")[1]
    offer = bot.post(
        "/api/bot/start",
        json={"user": {"id": 7777, "first_name": "Vadim"}, "payload": f"link_{code}"},
    ).json()["view"]
    assert "Вадим (vadim)" in offer["text"]
    assert offer["buttons"][0][0]["data"] == f"k:y:{code}"

    answer = bot.post(
        "/api/bot/link", json={"user": {"id": 7777, "username": "vad"}, "data": f"k:y:{code}"}
    ).json()
    assert answer["view"]["text"].startswith("✅ Telegram привязан")
    me = web.get("/api/auth/me").json()
    assert me["telegram_id"] == 7777 and me["name"] == "Вадим" and me["username"] == "vad"

    # Now the bot serves the account, and a used link does not work twice.
    assert (
        bot.post("/api/bot/messages", data={"text": "вес 80"})
        .json()["view"]["text"]
        .startswith("⚖️")
    )
    assert web.get("/api/weights").json()[0]["weight_kg"] == 80
    again = bot.post("/api/bot/link", json={"user": {"id": 7777}, "data": f"k:y:{code}"}).json()
    assert "устарела" in again["view"]["text"]


def test_one_telegram_for_one_account(app, bastion):
    first, second = browser(app), browser(app)
    sign_in(first, "vadim")
    sign_in(second, "daria")
    for client in (first, second):
        code = client.post("/api/auth/telegram-link").json()["link"].split("start=link_")[1]
        result = (
            browser(app)
            .post(
                "/api/bot/link",
                json={"user": {"id": 4242}, "data": f"k:y:{code}"},
                headers=bot_headers(4242),
            )
            .json()
        )
    assert "уже привязан к другому" in result["view"]["text"]
    assert second.get("/api/auth/me").json()["telegram_id"] is None


def test_hourly_sync_closes_access(app, bastion, sessions):
    web = browser(app)
    sign_in(web, "daria")
    assert web.get("/api/auth/me").status_code == 200
    bastion.allowed = {"b-vadim"}
    with sessions() as db:
        assert users.sync_bastion(db) == 1
    assert web.get("/api/auth/me").status_code == 401
    bastion.allowed = {"b-vadim", "b-daria"}
    with sessions() as db:
        assert users.sync_bastion(db) == 1
    assert sign_in(browser(app), "daria").status_code == 200
