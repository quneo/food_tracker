"""Meals sent from the site's «Записать» form: the assistant estimates them in the
background and the page asks how it went. Nothing of it goes to Telegram."""

from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from app.ai.jobs import worker
from app.ai.models import AiJob
from app.api.deps import CurrentUser, Db, Files
from app.chat.models import ChatMessage
from app.config import get_settings
from app.core.exceptions import DomainError, NotFound
from app.media import service as media
from app.nutrition import service as nutrition
from app.nutrition.models import Meal
from app.nutrition.schemas import MealOut
from app.users.models import User

router = APIRouter(tags=["assistant"])
MAX_PHOTOS = 6


class WebJob(BaseModel):
    id: int
    status: Literal["queued", "running", "done", "failed"]
    reply: str | None = None
    notes: list[str] = []
    meals: list[MealOut] = []
    error: str | None = None


def job_out(db, user: User, job: AiJob) -> dict:
    result = job.result or {}
    meals = [db.get(Meal, meal_id) for meal_id in result.get("meals", [])]
    return {
        "id": job.id,
        "status": job.status,
        "reply": result.get("reply") or None,
        "notes": result.get("notes", []),
        "meals": [
            nutrition.meal_out(meal, user) for meal in meals if meal and meal.user_id == user.id
        ],
        "error": result.get("error"),
    }


@router.post("/assistant/meals", response_model=WebJob, status_code=202)
def log_meal(
    user: CurrentUser,
    db: Db,
    files: Files,
    text: str = Form(default="", max_length=2000),
    mode: Literal["food", "label"] = Form(default="food"),
    photos: list[UploadFile] = File(default=[]),
):
    text = text.strip()
    if not text and not photos:
        raise DomainError("Добавьте фото или опишите, что съели")
    if len(photos) > MAX_PHOTOS:
        raise DomainError(f"Не больше {MAX_PHOTOS} фото за раз")
    if get_settings().ai_runner == "off":
        raise DomainError("Ассистент пока не подключен. Запишите прием пищи вручную", 503)
    message = ChatMessage(user_id=user.id, role="user", text=text, photos=len(photos))
    db.add(message)
    db.flush()
    for photo in photos:
        media.save_photo(db, files, user.id, photo.file.read(), "chat", message_id=message.id)
    job = AiJob(user_id=user.id, message_id=message.id, kind="web", result={"mode": mode})
    db.add(job)
    db.commit()
    worker.wake()
    return job_out(db, user, job)


@router.get("/assistant/jobs/{job_id}", response_model=WebJob)
def job_status(job_id: int, user: CurrentUser, db: Db):
    job = db.get(AiJob, job_id)
    if not job or job.user_id != user.id or job.kind != "web":
        raise NotFound()
    return job_out(db, user, job)
