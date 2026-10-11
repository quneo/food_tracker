"""The API the Telegram bot uses. Every call carries X-Bot-Secret; calls on behalf of a
person also carry X-Telegram-User."""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.ai.jobs import worker
from app.api.deps import BotUser, Db, Files, require_bot
from app.chat import outbox, service
from app.chat.models import OutboxMessage
from app.core.exceptions import DomainError

router = APIRouter(prefix="/bot", tags=["bot"], dependencies=[Depends(require_bot)])
MAX_PHOTOS = 6


class TelegramUser(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


class StartIn(BaseModel):
    user: TelegramUser
    payload: str | None = Field(default=None, max_length=128)


class PressIn(BaseModel):
    data: str = Field(max_length=64)
    # The message with the button: a started job's answer replaces it.
    message_id: int | None = None


class SentIn(BaseModel):
    message_id: int | None = None
    error: str | None = Field(default=None, max_length=300)
    permanent: bool = False


@router.post("/start")
def start(data: StartIn, db: Db):
    return {"view": service.start(db, data.user.model_dump(), data.payload)}


@router.post("/messages")
def receive(
    user: BotUser,
    db: Db,
    files: Files,
    text: str = Form(default="", max_length=4096),
    telegram_message_id: int | None = Form(default=None),
    status_message_id: int | None = Form(default=None),
    photos: list[UploadFile] = File(default=[]),
):
    if len(photos) > MAX_PHOTOS:
        raise DomainError(f"Не больше {MAX_PHOTOS} фото за раз")
    if not text.strip() and not photos:
        raise DomainError("Пустое сообщение")
    result = service.receive(
        db,
        files,
        user,
        text,
        [photo.file.read() for photo in photos],
        telegram_message_id,
        status_message_id,
    )
    if result["job_id"]:
        worker.wake()
    return result


class LinkIn(BaseModel):
    user: TelegramUser
    code: str | None = Field(default=None, max_length=64)


@router.post("/link")
def link(data: LinkIn, db: Db):
    """/link <key> from a Telegram account that may not be known yet."""
    return {"view": service.link(db, data.user.model_dump(), data.code)}


@router.post("/press")
def press(data: PressIn, user: BotUser, db: Db):
    result = service.press(db, user, data.data, data.message_id)
    if result.get("job_id"):
        worker.wake()
    return result


@router.get("/review")
def review_menu(user: BotUser):
    return {"view": service.review_menu()}


@router.get("/today")
def today(user: BotUser, db: Db):
    return {"view": service.today(db, user)}


@router.post("/new")
def new_conversation(user: BotUser, db: Db):
    return {"view": service.new_conversation(db, user)}


@router.post("/progress-mode")
def progress_mode(user: BotUser, db: Db):
    return {"view": service.progress_mode(db, user)}


@router.get("/app")
def app_link(user: BotUser):
    return {"view": service.app_link()}


@router.get("/outbox")
def pending(db: Db):
    return [
        {"id": message.id, "chat_id": message.chat_id, **message.payload}
        for message in outbox.pending(db)
    ]


@router.post("/outbox/{message_id}")
def sent(message_id: int, data: SentIn, db: Db):
    message = db.get(OutboxMessage, message_id)
    if not message:
        raise DomainError("Нет такого сообщения", 404)
    outbox.report(db, message, data.message_id, data.error, data.permanent)
    return {"status": message.status}
