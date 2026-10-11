from datetime import date
from typing import Literal

from fastapi import APIRouter, File, Query, Response, UploadFile

from app.api.deps import CurrentUser, Db, Files
from app.core.exceptions import DomainError
from app.core.timeutil import local_today, zone
from app.media import service as media
from app.nutrition import service
from app.nutrition.schemas import DaySummary, MealIn, MealOut, MealPatch, MealType

router = APIRouter(tags=["meals"])
MAX_PHOTOS = 6


@router.get("/meals", response_model=list[MealOut])
def list_meals(
    user: CurrentUser,
    db: Db,
    start: date = Query(alias="from"),
    end: date = Query(alias="to"),
    meal_type: MealType | None = None,
    status: Literal["draft", "confirmed"] | None = None,
):
    meals = service.list_meals(db, user.id, start, end, meal_type, status)
    return [service.meal_out(meal, user) for meal in meals]


@router.post("/meals", response_model=MealOut, status_code=201)
def create_meal(data: MealIn, user: CurrentUser, db: Db):
    meal = service.create(db, user, data)
    db.commit()
    db.refresh(meal)
    return service.meal_out(meal, user)


@router.get("/meals/{meal_id}", response_model=MealOut)
def get_meal(meal_id: int, user: CurrentUser, db: Db):
    return service.meal_out(service.owned(db, meal_id, user.id), user)


@router.patch("/meals/{meal_id}", response_model=MealOut)
def update_meal(meal_id: int, data: MealPatch, user: CurrentUser, db: Db):
    meal = service.owned(db, meal_id, user.id)
    service.update(db, user, meal, data)
    db.commit()
    db.refresh(meal)
    return service.meal_out(meal, user)


@router.post("/meals/{meal_id}/confirm", response_model=MealOut)
def confirm_meal(meal_id: int, user: CurrentUser, db: Db):
    meal = service.owned(db, meal_id, user.id)
    service.confirm(meal)
    db.commit()
    return service.meal_out(meal, user)


@router.delete("/meals/{meal_id}", status_code=204)
def delete_meal(meal_id: int, user: CurrentUser, db: Db, files: Files):
    service.delete(db, service.owned(db, meal_id, user.id))
    db.commit()
    media.purge(db, files)
    return Response(status_code=204)


@router.post("/meals/{meal_id}/photos", response_model=MealOut)
def add_photo(meal_id: int, user: CurrentUser, db: Db, files: Files, photo: UploadFile = File()):
    meal = service.owned(db, meal_id, user.id)
    if len(meal.photos) >= MAX_PHOTOS:
        raise DomainError(f"К одному приему пищи — не больше {MAX_PHOTOS} фото")
    media.save_photo(db, files, user.id, photo.file.read(), "meal", meal_id=meal.id)
    db.commit()
    db.refresh(meal)
    return service.meal_out(meal, user)


@router.delete("/meals/{meal_id}/photos/{media_id}", response_model=MealOut)
def delete_photo(meal_id: int, media_id: int, user: CurrentUser, db: Db, files: Files):
    meal = service.owned(db, meal_id, user.id)
    item = media.owned(db, media_id, user.id)
    if item.meal_id != meal.id:
        raise DomainError("Фото не относится к этому приему пищи", 404)
    media.drop(db, [item])
    db.commit()
    media.purge(db, files)
    db.refresh(meal)
    return service.meal_out(meal, user)


@router.get("/days/{day}", response_model=DaySummary)
def day(day: date, user: CurrentUser, db: Db):
    return service.day_summary(db, user, day)


@router.get("/today", response_model=DaySummary)
def today(user: CurrentUser, db: Db):
    return service.day_summary(db, user, local_today(zone(user.profile.timezone)))
