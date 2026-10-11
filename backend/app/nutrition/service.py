from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, NotFound
from app.core.timeutil import from_local, local_day, local_now, to_local, zone
from app.database import utcnow
from app.media import service as media
from app.nutrition.models import Meal, MealItem
from app.nutrition.schemas import MealIn, MealPatch
from app.users.models import User

MAX_RANGE_DAYS = 400


def tz_of(user: User):
    return zone(user.profile.timezone)


def meal_out(meal: Meal, user: User) -> dict:
    tz = tz_of(user)
    return {
        "id": meal.id,
        "status": meal.status,
        "meal_type": meal.meal_type,
        "title": meal.title,
        "eaten_at": to_local(meal.eaten_at, tz).isoformat(timespec="minutes"),
        "eaten_on": meal.eaten_on,
        "note": meal.note,
        "source": meal.source,
        "kcal": meal.kcal,
        "protein": meal.protein,
        "fat": meal.fat,
        "carbs": meal.carbs,
        "estimated_by": meal.estimated_by,
        "confidence": meal.confidence,
        "kcal_low": meal.kcal_low,
        "kcal_high": meal.kcal_high,
        "assumptions": meal.assumptions or [],
        "ai_comment": meal.ai_comment,
        "items": meal.items,
        "photos": meal.photos,
        "created_at": to_local(meal.created_at, tz).isoformat(timespec="minutes"),
    }


def owned(db: Session, meal_id: int, user_id: int) -> Meal:
    meal = db.get(Meal, meal_id)
    if not meal or meal.user_id != user_id:
        raise NotFound("Прием пищи не найден")
    return meal


def check_range(start: date, end: date):
    if end < start:
        raise DomainError("Начало периода позже конца")
    if (end - start).days > MAX_RANGE_DAYS:
        raise DomainError(f"Период не длиннее {MAX_RANGE_DAYS} дней")


def list_meals(
    db: Session,
    user_id: int,
    start: date,
    end: date,
    meal_type: str | None = None,
    status: str | None = None,
) -> list[Meal]:
    check_range(start, end)
    query = select(Meal).where(
        Meal.user_id == user_id, Meal.eaten_on >= start, Meal.eaten_on <= end
    )
    if meal_type:
        query = query.where(Meal.meal_type == meal_type)
    if status:
        query = query.where(Meal.status == status)
    return list(db.scalars(query.order_by(Meal.eaten_at.desc(), Meal.id.desc())))


def guess_meal_type(local: datetime) -> str:
    hour = local.hour
    if 5 <= hour < 11:
        return "breakfast"
    if 11 <= hour < 16:
        return "lunch"
    if 17 <= hour < 23:
        return "dinner"
    return "snack"


def set_time(meal: Meal, user: User, local: datetime | None):
    """Sets eaten_at/eaten_on from local wall time (now when None)."""
    tz = tz_of(user)
    if local is None:
        meal.eaten_at = utcnow()
    else:
        when = from_local(local, tz)
        if when > utcnow() + timedelta(hours=1):
            raise DomainError("Время приема пищи в будущем")
        meal.eaten_at = when
    meal.eaten_on = local_day(meal.eaten_at, tz)


def own_products(db: Session, user_id: int, items: list) -> list:
    """Drops links to products that are not the person's own."""
    from app.nutrition.products import owned_ids

    mine = owned_ids(db, user_id, {item.product_id for item in items if item.product_id})
    for item in items:
        if item.product_id not in mine:
            item.product_id = None
    return items


def set_items(meal: Meal, items: list) -> None:
    meal.items = [
        MealItem(position=position, **item.model_dump()) for position, item in enumerate(items)
    ]
    meal.recount()


def create(
    db: Session,
    user: User,
    data: MealIn,
    *,
    source: str = "manual",
    status: str = "confirmed",
    estimated_by: str = "user",
) -> Meal:
    meal = Meal(
        user_id=user.id,
        title=data.title.strip(),
        note=data.note,
        source=source,
        status=status,
        estimated_by=estimated_by,
        assumptions=[],
    )
    set_time(meal, user, data.eaten_at)
    meal.meal_type = data.meal_type or guess_meal_type(to_local(meal.eaten_at, tz_of(user)))
    set_items(meal, own_products(db, user.id, data.items))
    if status == "confirmed":
        meal.confirmed_at = utcnow()
    db.add(meal)
    db.flush()
    return meal


def update(db: Session, user: User, meal: Meal, data: MealPatch) -> Meal:
    fields = data.model_fields_set
    if "title" in fields and data.title:
        meal.title = data.title.strip()
    if "meal_type" in fields:
        meal.meal_type = data.meal_type
    if "note" in fields:
        meal.note = data.note
    if "eaten_at" in fields and data.eaten_at:
        set_time(meal, user, data.eaten_at)
    if "items" in fields and data.items:
        set_items(meal, own_products(db, user.id, data.items))
        # The person changed the numbers: the result is theirs, not a guess anymore.
        meal.estimated_by = "user"
        meal.confidence = None
        meal.kcal_low = meal.kcal_high = None
        meal.assumptions = []
    db.flush()
    return meal


def confirm(meal: Meal):
    if meal.status != "confirmed":
        meal.status = "confirmed"
        meal.confirmed_at = utcnow()


def delete(db: Session, meal: Meal):
    media.drop(db, list(meal.photos))
    db.delete(meal)


def totals(meals: list[Meal]) -> dict:
    confirmed = [meal for meal in meals if meal.status == "confirmed"]
    return {
        field: round(sum(getattr(meal, field) for meal in confirmed), 1)
        for field in ("kcal", "protein", "fat", "carbs")
    }


def targets(user: User) -> dict:
    profile = user.profile
    return {
        "kcal": profile.kcal_target,
        "protein": profile.protein_target,
        "fat": profile.fat_target,
        "carbs": profile.carbs_target,
    }


def day_summary(db: Session, user: User, day: date | None = None) -> dict:
    day = day or local_now(tz_of(user)).date()
    meals = list_meals(db, user.id, day, day)
    meals.sort(key=lambda meal: meal.eaten_at)
    return {
        "day": day,
        "totals": totals(meals),
        "targets": targets(user),
        "meals": [meal_out(meal, user) for meal in meals],
        "drafts": sum(meal.status == "draft" for meal in meals),
    }
