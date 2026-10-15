"""Edits of a recorded meal, item by item.

What the assistant proposes ("add plums", "the rice was 200 g", "no oil") becomes the
meal's new list of items plus a short list of what changes; items nobody mentioned stay
exactly as they were. A snapshot taken before the change lets one tap put it back."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from app.ai.schemas import EditMeal, FoodItem, ItemChange
from app.chat import views
from app.core.exceptions import DomainError
from app.core.timeutil import parse_local, to_local, zone
from app.nutrition import products as product_store
from app.nutrition import service as nutrition
from app.nutrition.models import Meal, MealItem, Product
from app.nutrition.schemas import MealItemIn
from app.users.models import User

FIELDS = ("kcal", "protein", "fat", "carbs")
TYPES = {"breakfast": "завтрак", "lunch": "обед", "dinner": "ужин", "snack": "перекус"}
FindProduct = Callable[[int | None], Product | None]


@dataclass
class Plan:
    items: list[MealItemIn]
    lines: list[str]  # "+ Сливы, 105 г — 48 ккал", what the person sees
    title: str | None
    meal_type: str | None
    eaten_at: str | None  # local "YYYY-MM-DDTHH:MM"
    comment: str | None
    only_added: bool

    @property
    def kcal(self) -> float:
        return sum(item.kcal for item in self.items)

    def dump(self) -> dict:
        return {
            "items": [item.model_dump() for item in self.items],
            "lines": self.lines,
            "title": self.title,
            "meal_type": self.meal_type,
            "eaten_at": self.eaten_at,
            "comment": self.comment,
            "only_added": self.only_added,
        }

    @classmethod
    def load(cls, data: dict) -> "Plan":
        return cls(**{**data, "items": [MealItemIn(**item) for item in data["items"]]})


def from_record(item: MealItem) -> MealItemIn:
    return MealItemIn(
        name=item.name,
        product_id=item.product_id,
        grams=item.grams,
        grams_source=item.grams_source,
        kcal=item.kcal,
        protein=item.protein,
        fat=item.fat,
        carbs=item.carbs,
        confidence=item.confidence,
        note=item.note,
    )


def from_estimate(item: FoodItem, find: FindProduct) -> MealItemIn:
    """An item the assistant estimated; a saved product's label decides its numbers."""
    grams = item.grams if item.grams and item.grams > 0 else None
    values = {field: getattr(item, field) for field in FIELDS}
    product = find(item.product_id)
    if product:
        grams = grams or product.portion_grams or product.package_grams
        if grams:
            values = product_store.scaled(product, grams)
        product_store.used(product)
    return MealItemIn(
        name=item.name.strip()[:200] or "Без названия",
        product_id=product.id if product else None,
        grams=grams,
        grams_source=item.grams_source,
        confidence=item.confidence,
        note=(item.note or "")[:300] or None,
        **values,
    )


def _changed(item: MealItemIn, change: ItemChange, find: FindProduct) -> MealItemIn:
    values = item.model_dump()
    if change.name and change.name.strip():
        values["name"] = change.name.strip()[:200]
    given = {
        field: getattr(change, field) for field in FIELDS if getattr(change, field) is not None
    }
    grams = change.grams if change.grams and change.grams > 0 else None
    if grams and grams != item.grams:
        product = find(item.product_id)
        if not given:
            if product:
                given = product_store.scaled(product, grams)
            elif item.grams:
                # Same food, another amount: the numbers follow the weight.
                ratio = grams / item.grams
                given = {field: round(values[field] * ratio, 1) for field in FIELDS}
            else:
                raise DomainError(f"для «{values['name']}» нужны калории, не только вес")
        values["grams"] = grams
        values["grams_source"] = change.grams_source or "stated"
    values.update(given)
    return MealItemIn(**values)


def _weight(item) -> str:
    if not item.grams:
        return ""
    approx = "~" if item.grams_source == "estimated" else ""
    return f", {approx}{views.n(item.grams)} г"


def describe(item) -> str:
    return f"{item.name}{_weight(item)} — {views.n(item.kcal)} ккал"


def _difference(before: MealItem, after: MealItemIn) -> str | None:
    parts = []
    if (before.grams or 0) != (after.grams or 0):
        parts.append(f"{views.n(before.grams)} → {views.n(after.grams)} г")
    if views.n(before.kcal) != views.n(after.kcal):
        parts.append(f"{views.n(before.kcal)} → {views.n(after.kcal)} ккал")
    renamed = after.name != before.name
    if not parts and not renamed:
        return None
    name = f"{before.name} → {after.name}" if renamed else after.name
    return f"✎ {name}" + (f": {', '.join(parts)}" if parts else "")


def plan(meal: Meal, action: EditMeal, find: FindProduct, tz_name: str) -> Plan:
    known = {item.id: item for item in meal.items}
    for item_id in [*action.remove, *(change.item_id for change in action.change)]:
        if item_id not in known:
            raise DomainError(f"в «{meal.title}» нет позиции #{item_id}")
    removed = set(action.remove)
    changes = {change.item_id: change for change in action.change if change.item_id not in removed}
    items, lines, edited = [], [], False
    for record in meal.items:
        if record.id in removed:
            lines.append(f"− {describe(record)}")
            continue
        item = from_record(record)
        if record.id in changes:
            item = _changed(item, changes[record.id], find)
            line = _difference(record, item)
            if line:
                lines.append(line)
                edited = True
        items.append(item)
    for food in action.add:
        item = from_estimate(food, find)
        items.append(item)
        lines.append(f"+ {describe(item)}")
    if not items:
        raise DomainError("в записи не останется ни одного продукта")

    tz = zone(tz_name)
    meal_type = action.meal_type if action.meal_type != meal.meal_type else None
    if meal_type:
        lines.append(f"Тип: {TYPES.get(meal.meal_type or '', '—')} → {TYPES[meal_type]}")
    when = parse_local(action.eaten_at)
    eaten_at = None
    if when:
        old = to_local(meal.eaten_at, tz)
        if when.replace(second=0, microsecond=0) != old.replace(
            tzinfo=None, second=0, microsecond=0
        ):
            eaten_at = when.strftime("%Y-%m-%dT%H:%M")
            lines.append(f"Время: {old:%d.%m %H:%M} → {when:%d.%m %H:%M}")
    title = (action.title or "").strip()[:200] or None
    if title == meal.title:
        title = None
    comment = (action.comment or "").strip()[:1500] or None
    return Plan(
        items=items,
        lines=lines,
        title=title,
        meal_type=meal_type,
        eaten_at=eaten_at,
        comment=comment,
        only_added=bool(action.add)
        and not removed
        and not edited
        and not meal_type
        and not eaten_at,
    )


def apply(meal: Meal, plan: Plan, user: User):
    old_kcal = meal.kcal
    if plan.title:
        meal.title = plan.title
    if plan.eaten_at:
        nutrition.set_time(meal, user, parse_local(plan.eaten_at))
    if plan.meal_type:
        meal.meal_type = plan.meal_type
    nutrition.set_items(meal, plan.items)
    # The honest range moves with the total; what was certain stays certain.
    if meal.kcal_low is not None and meal.kcal_high is not None:
        delta = meal.kcal - old_kcal
        meal.kcal_low = round(max(0, min(meal.kcal_low + delta, meal.kcal)))
        meal.kcal_high = round(max(meal.kcal_high + delta, meal.kcal))
    if plan.comment:
        meal.ai_comment = plan.comment


def summary(meal: Meal, plan: Plan) -> str:
    return (
        f"Изменить «{meal.title}» ({meal.eaten_on:%d.%m})?\n"
        + "\n".join(plan.lines)
        + f"\nИтого: {views.n(meal.kcal)} → {views.n(plan.kcal)} ккал"
    )


def fingerprint(meal: Meal) -> list:
    """What the items were when a change was proposed: a change waits for a yes, and the
    meal may be edited on the site meanwhile."""
    return [[item.name, item.grams, round(item.kcal, 1)] for item in meal.items]


def snapshot(meal: Meal) -> dict:
    return {
        "meal_id": meal.id,
        "title": meal.title,
        "meal_type": meal.meal_type,
        "eaten_at": meal.eaten_at.isoformat(),
        "eaten_on": meal.eaten_on.isoformat(),
        "kcal_low": meal.kcal_low,
        "kcal_high": meal.kcal_high,
        "ai_comment": meal.ai_comment,
        "items": [from_record(item).model_dump() for item in meal.items],
    }


def restore(meal: Meal, saved: dict):
    meal.title = saved["title"]
    meal.meal_type = saved["meal_type"]
    meal.eaten_at = datetime.fromisoformat(saved["eaten_at"])
    meal.eaten_on = date.fromisoformat(saved["eaten_on"])
    nutrition.set_items(meal, [MealItemIn(**item) for item in saved["items"]])
    meal.kcal_low = saved["kcal_low"]
    meal.kcal_high = saved["kcal_high"]
    meal.ai_comment = saved["ai_comment"]
