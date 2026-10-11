import os

BOT_TOKEN = "123456:TEST-token-for-signatures-only"
BOT_SECRET = "test-bot-secret-" * 3
os.environ.update(
    DATABASE_URL="sqlite://",
    BOT_API_SECRET=BOT_SECRET,
    TELEGRAM_BOT_TOKEN=BOT_TOKEN,
    TELEGRAM_BOT_USERNAME="food_test_bot",
    PUBLIC_URL="https://food.example.com",
    REGISTRATION="invite",
    ADMIN_TELEGRAM_IDS="1001",
    DEFAULT_TIMEZONE="Asia/Krasnoyarsk",
    S3_ACCESS_KEY="test",
    S3_SECRET_KEY="test-secret",
    AI_RUNNER="ssh",
    AI_SSH_TARGET="food-ai@vps.example",
)

import hashlib
import hmac
import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.ai import jobs
from app.ai.runner import RunnerResult
from app.api.deps import storage
from app.database import Base, configure_sqlite, get_db
from app.media.storage import MemoryStorage

main.BACKGROUND["enabled"] = False


@pytest.fixture
def sessions():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    configure_sqlite(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def files():
    return MemoryStorage()


class FakeRunner:
    """Stands in for Codex: returns queued answers and records the prompts."""

    def __init__(self):
        self.answers = []
        self.calls = []

    async def __call__(self, prompt, schema, images):
        self.calls.append({"prompt": prompt, "schema": schema, "images": images})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return RunnerResult(
            answer, "gpt-test", 1000, 200, 1234, cached_input_tokens=800, reasoning_output_tokens=50
        )


@pytest.fixture
def runner():
    return FakeRunner()


@pytest.fixture
def worker(sessions, files, runner, monkeypatch):
    test_worker = jobs.Worker(sessions=sessions, storage=files, run=runner)
    monkeypatch.setattr(jobs, "worker", test_worker)
    monkeypatch.setattr("app.api.bot.worker", test_worker)
    return test_worker


@pytest.fixture
def app(sessions, files, worker):
    def override_db():
        with sessions() as session:
            yield session

    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[storage] = lambda: files
    yield main.app
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def widget_payload(telegram_id: int, first_name: str = "Test", **extra) -> dict:
    fields = {
        "id": telegram_id,
        "first_name": first_name,
        "auth_date": int(time.time()),
        **extra,
    }
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return fields


def bot_headers(telegram_id: int) -> dict:
    return {"X-Bot-Secret": BOT_SECRET, "X-Telegram-User": str(telegram_id)}


class Person:
    """A user that talks to the bot API and has its own signed-in web client."""

    def __init__(self, app, telegram_id: int, name: str):
        self.telegram_id = telegram_id
        self.bot = TestClient(app, base_url="https://testserver")
        self.web = TestClient(app, base_url="https://testserver")
        self.bot.headers.update(bot_headers(telegram_id))
        response = self.bot.post(
            "/api/bot/start", json={"user": {"id": telegram_id, "first_name": name}}
        )
        assert response.status_code == 200, response.text
        response = self.web.post("/api/auth/telegram", json=widget_payload(telegram_id, name))
        assert response.status_code == 200, response.text

    def say(self, text: str = "", photos: list[bytes] | None = None, status_message_id=500):
        files = [
            ("photos", (f"{n}.jpg", data, "image/jpeg")) for n, data in enumerate(photos or [])
        ]
        return self.bot.post(
            "/api/bot/messages",
            data={"text": text, "status_message_id": str(status_message_id)},
            files=files or None,
        )

    def press(self, data: str) -> dict:
        response = self.bot.post("/api/bot/press", json={"data": data})
        assert response.status_code == 200, response.text
        return response.json()


@pytest.fixture
def admin(app):
    return Person(app, 1001, "Admin")


@pytest.fixture
def invite_link(admin):
    response = admin.web.post("/api/admin/invites", json={"note": "test", "max_uses": 2})
    assert response.status_code == 201, response.text
    return response.json()["link"]


@pytest.fixture
def make_person(app, invite_link):
    code = invite_link.split("start=")[1]

    def make(telegram_id: int, name: str = "User") -> Person:
        client = TestClient(app, base_url="https://testserver")
        client.headers.update(bot_headers(telegram_id))
        joined = client.post(
            "/api/bot/start",
            json={"user": {"id": telegram_id, "first_name": name}, "payload": code},
        )
        assert joined.status_code == 200
        return Person(app, telegram_id, name)

    return make


def jpeg(color=(200, 120, 40), size=(64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "JPEG")
    return buffer.getvalue()
