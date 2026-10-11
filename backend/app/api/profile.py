from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, Db
from app.core.exceptions import DomainError
from app.core.timeutil import local_today, valid_zone, zone
from app.nutrition import targets
from app.progress import service as progress
from app.reminders import service as reminders
from app.reminders.models import Reminder

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileIn(BaseModel):
    sex: Literal["male", "female"] | None = None
    birth_date: date | None = None
    height_cm: float | None = Field(default=None, ge=100, le=250)
    activity: Literal["sedentary", "light", "moderate", "high", "very_high"] | None = None
    goal: Literal["lose", "maintain", "gain"] | None = None
    target_weight_kg: float | None = Field(default=None, ge=30, le=300)
    kcal_target: int | None = Field(default=None, ge=800, le=6000)
    protein_target: int | None = Field(default=None, ge=0, le=500)
    fat_target: int | None = Field(default=None, ge=0, le=400)
    carbs_target: int | None = Field(default=None, ge=0, le=1000)
    timezone: str = Field(min_length=1, max_length=64)
    about: str | None = Field(default=None, max_length=2000)
    auto_confirm_meals: bool = False


FIELDS = list(ProfileIn.model_fields)


def profile_out(user) -> dict:
    profile = user.profile
    return {field: getattr(profile, field) for field in FIELDS}


@router.get("")
def read_profile(user: CurrentUser):
    return profile_out(user)


@router.put("")
def save_profile(data: ProfileIn, user: CurrentUser, db: Db):
    if not valid_zone(data.timezone):
        raise DomainError("Неизвестный часовой пояс")
    today = local_today(zone(data.timezone))
    if data.birth_date and not date(1900, 1, 1) < data.birth_date < today:
        raise DomainError("Проверьте дату рождения")
    profile = user.profile
    moved = profile.timezone != data.timezone
    for field in FIELDS:
        setattr(profile, field, getattr(data, field))
    if moved:
        for reminder in db.query(Reminder).filter(Reminder.user_id == user.id):
            reminders.reschedule(reminder, data.timezone)
    db.commit()
    return profile_out(user)


@router.get("/suggested-targets")
def suggested_targets(user: CurrentUser, db: Db):
    profile = user.profile
    weight = progress.latest_weight(db, user.id)
    result = targets.suggest(
        profile.sex,
        profile.birth_date,
        profile.height_cm,
        weight.weight_kg if weight else None,
        profile.activity,
        profile.goal,
        local_today(zone(profile.timezone)),
    )
    if not result:
        raise DomainError("Для расчета нужны пол, дата рождения, рост и хотя бы одно взвешивание")
    return result
