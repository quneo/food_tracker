"""Turns the assistant's proposed actions into changes, after checking each one.

The model never touches the database. Every action is validated here: ids must belong to
the person and be of the right kind, numbers must be plausible. New records are written
at once (with an undo button). Edits of a recorded meal apply at once too, with a button
that puts the meal back; deletions of saved records wait for a "yes"."""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai import meal_edits, memory
from app.ai.models import MemoryFact
from app.ai.schemas import (
    CreateMeal,
    DeleteMeal,
    DeleteProduct,
    DeleteRecord,
    DeleteReminder,
    EditMeal,
    Forget,
    LogMeasurements,
    LogWeight,
    MealEstimate,
    Remember,
    SaveNote,
    SaveProduct,
    SaveProgressPhoto,
    SetReminder,
    TurnResult,
    UpdateMemory,
    UpdateProfile,
    UpdateWeight,
)
from app.chat import views
from app.chat.models import PendingAction
from app.core.exceptions import DomainError
from app.core.timeutil import local_today, parse_local, to_local, valid_zone, zone
from app.database import utcnow
from app.media.models import Media
from app.notes import service as notes
from app.nutrition import products as product_store
from app.nutrition import service as nutrition
from app.nutrition.models import Meal, Product
from app.nutrition.schemas import ProductIn
from app.progress import daily
from app.progress import service as progress
from app.progress.models import MEASUREMENTS, Measurement, ProgressPhoto, WeightEntry
from app.reminders import service as reminders
from app.reminders.models import Reminder
from app.users.models import User

log = logging.getLogger(__name__)
PENDING_TTL = timedelta(hours=24)
ENTITY_NAMES = {"weight": "вес", "measurement": "замер", "progress_photo": "фото прогресса"}
# What did not happen when an action was refused, in the person's words.
REFUSED = {
    "create_meal": "Не записал прием пищи",
    "edit_meal": "Не изменил запись",
    "delete_meal": "Не удалил запись",
    "log_weight": "Не записал вес",
    "log_measurements": "Не записал замеры",
    "save_progress_photo": "Не сохранил фото",
    "save_product": "Не сохранил продукт",
    "update_profile": "Не обновил профиль",
    "set_reminder": "Не поставил напоминание",
    "save_note": "Не сохранил заметку",
}


@dataclass
class Outcome:
    notes: list[str] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)
    created: list[list] = field(default_factory=list)  # [entity, id] the undo button removes
    meals: list[int] = field(default_factory=list)  # meals created or changed, for the site


class Executor:
    def __init__(
        self,
        db: Session,
        user: User,
        photos: list[Media],
        model: str | None,
        focus_meal_id: int | None,
    ):
        self.db = db
        self.user = user
        self.photos = [photo for photo in photos if photo.kind == "chat"]
        self.model = model
        self.focus_meal_id = focus_meal_id
        self.tz_name = user.profile.timezone
        self.out = Outcome()

    def run(self, result: TurnResult) -> Outcome:
        handlers = {
            "create_meal": self.create_meal,
            "edit_meal": self.edit_meal,
            "delete_meal": self.delete_meal,
            "log_weight": self.log_weight,
            "update_weight": self.update_weight,
            "log_measurements": self.log_measurements,
            "save_progress_photo": self.save_progress_photo,
            "delete_record": self.delete_record,
            "remember": self.remember,
            "update_memory": self.update_memory,
            "forget": self.forget,
            "update_profile": self.update_profile,
            "set_reminder": self.set_reminder,
            "delete_reminder": self.delete_reminder,
            "save_product": self.save_product,
            "delete_product": self.delete_product,
            "save_note": self.save_note,
        }
        for action in result.actions[:12]:
            try:
                with self.db.begin_nested():
                    handlers[action.kind](action)
            except (DomainError, ValidationError, ValueError) as error:
                message = error.message if isinstance(error, DomainError) else "неверные данные"
                log.info("action %s rejected: %s", action.kind, error)
                what = REFUSED.get(action.kind, "Не получилось")
                self.out.notes.append(f"⚠️ {what}: {message[:1].lower()}{message[1:]}")
        return self.out

    # Helpers

    def day_total(self) -> dict:
        today = local_today(zone(self.tz_name))
        return nutrition.totals(nutrition.list_meals(self.db, self.user.id, today, today))

    def card(self, meal: Meal, changes: list[str] | None = None, restore: int | None = None):
        card = views.meal_view(
            meal, self.tz_name, self.day_total(), nutrition.targets(self.user), changes=changes
        )
        if meal.id not in self.out.meals:
            self.out.meals.append(meal.id)
        if restore:
            back = views.button("↩️ Вернуть как было", f"u:{restore}")
            card["buttons"] = card["buttons"] + [[back]]
        self.out.cards.append(card)

    def ask(self, kind: str, payload: dict, summary: str):
        action = PendingAction(
            user_id=self.user.id,
            kind=kind,
            payload=payload,
            summary=summary,
            expires_at=utcnow() + PENDING_TTL,
        )
        self.db.add(action)
        self.db.flush()
        self.out.cards.append(views.confirm_view(action.id, summary, kind.startswith("delete")))

    def owned(self, model, record_id: int, what: str):
        record = self.db.get(model, record_id)
        if not record or record.user_id != self.user.id:
            raise DomainError(f"не нашел {what} #{record_id}")
        return record

    def product(self, product_id: int | None) -> Product | None:
        if not product_id:
            return None
        product = self.db.get(Product, product_id)
        return product if product and product.user_id == self.user.id else None

    def apply_estimate(self, meal: Meal, estimate: MealEstimate):
        # A saved product: its label decides the numbers, the model only the amount.
        items = [meal_edits.from_estimate(item, self.product) for item in estimate.items]
        if not items:
            raise DomainError("в оценке нет ни одного продукта")
        meal.title = estimate.title.strip()[:200] or "Прием пищи"
        when = parse_local(estimate.eaten_at)
        if when or not meal.eaten_at:
            nutrition.set_time(meal, self.user, when)
        if estimate.meal_type:
            meal.meal_type = estimate.meal_type
        elif not meal.meal_type:
            meal.meal_type = nutrition.guess_meal_type(
                when or to_local(meal.eaten_at, zone(self.tz_name))
            )
        nutrition.set_items(meal, items)
        meal.estimated_by = "ai"
        meal.confidence = estimate.confidence
        low, high = sorted([max(estimate.kcal_low, 0), max(estimate.kcal_high, 0)])
        meal.kcal_low = round(min(low, meal.kcal))
        meal.kcal_high = round(max(high, meal.kcal))
        meal.assumptions = [text.strip()[:200] for text in estimate.assumptions if text.strip()][:8]
        meal.ai_comment = (estimate.comment or "").strip()[:1500] or None
        meal.ai_model = self.model

    # Meals

    def create_meal(self, action: CreateMeal):
        auto = self.user.profile.auto_confirm_meals
        photos = self.photos if action.use_photos else []
        meal = Meal(
            user_id=self.user.id,
            status="confirmed" if auto else "draft",
            source="photo" if photos else "text",
            confirmed_at=utcnow() if auto else None,
        )
        self.apply_estimate(meal, action.meal)
        self.db.add(meal)
        self.db.flush()
        for photo in photos:
            photo.kind = "meal"
            photo.meal_id = meal.id
        self.photos = [photo for photo in self.photos if photo not in photos]
        if action.note_id:
            try:
                notes.use(notes.usable(self.db, action.note_id, self.user.id), meal.id)
            except DomainError:
                # A stale note never costs the meal itself.
                log.info("note %s not usable for meal %s", action.note_id, meal.id)
        self.db.flush()
        self.db.refresh(meal)
        self.card(meal)

    def edit_meal(self, action: EditMeal):
        """Only what was named changes, at once: the person already said what to do. A
        recorded meal gets a button that puts it back as it was."""
        meal = self.owned(Meal, action.meal_id, "прием пищи")
        plan = meal_edits.plan(meal, action, self.product, self.tz_name)
        if not plan.lines and not plan.title and not plan.comment:
            raise DomainError("в записи нечего менять")
        restore = None
        if meal.status != "draft":
            # A recorded meal: one tap puts it back as it was.
            back = PendingAction(
                user_id=self.user.id,
                kind="restore_meal",
                payload=meal_edits.snapshot(meal),
                summary=f"Вернуть «{meal.title}» как было",
                expires_at=utcnow() + PENDING_TTL,
            )
            self.db.add(back)
            self.db.flush()
            restore = back.id
        meal_edits.apply(meal, plan, self.user)
        self.db.flush()
        self.db.refresh(meal)
        self.card(meal, plan.lines, restore)

    def delete_meal(self, action: DeleteMeal):
        meal = self.owned(Meal, action.meal_id, "прием пищи")
        if meal.status == "draft":
            self.out.notes.append(f"🗑 Удалил черновик «{meal.title}»")
            nutrition.delete(self.db, meal)
        else:
            self.ask(
                "delete_meal",
                {"meal_id": meal.id},
                f"Удалить «{meal.title}» ({meal.eaten_on:%d.%m}, {views.n(meal.kcal)} ккал)?",
            )

    # Body

    def log_weight(self, action: LogWeight):
        # One weight a day: a second one asks whether to replace the first.
        entry, ask = daily.weight(
            self.db, self.user, action.weight_kg, parse_local(action.measured_at)
        )
        if ask:
            self.out.cards.append(daily.replace_view(ask))
            return
        self.out.notes.append(f"⚖️ Записал вес: {views.n(entry.weight_kg, 1)} кг")
        self.out.created.append(["weight", entry.id])

    def update_weight(self, action: UpdateWeight):
        entry = self.owned(WeightEntry, action.weight_id, "запись веса")
        if not 20 <= action.weight_kg <= 400:
            raise DomainError("вес должен быть от 20 до 400 кг")
        self.ask(
            "update_weight",
            {"weight_id": entry.id, "weight_kg": action.weight_kg},
            f"Исправить вес за {entry.measured_on:%d.%m}: {views.n(entry.weight_kg, 1)} → "
            f"{views.n(action.weight_kg, 1)} кг?",
        )

    def log_measurements(self, action: LogMeasurements):
        when = parse_local(action.measured_at)
        values = {value.kind: value.value for value in action.values}
        entries, ask = daily.measurements(self.db, self.user, values, when)
        saved = []
        for entry in entries:
            self.out.created.append(["measurement", entry.id])
            name, unit = MEASUREMENTS[entry.kind]
            saved.append(f"{name.lower()} {views.n(entry.value, 1)} {'%' if unit == '%' else 'см'}")
        if saved:
            self.out.notes.append("📏 Записал замеры: " + ", ".join(saved))
        if ask:
            self.out.cards.append(daily.replace_view(ask))

    def save_progress_photo(self, action: SaveProgressPhoto):
        if not self.photos:
            raise DomainError("в сообщении нет фото")
        # Several photos are one entry: front, back, side unless told otherwise. A day
        # that already has photos asks first.
        records, ask = daily.progress_photos(
            self.db, self.user, list(self.photos), action.note, action.pose
        )
        self.photos = []
        if ask:
            self.out.cards.append(daily.replace_view(ask, add=True))
            return
        for record in records:
            self.out.created.append(["progress_photo", record.id])
        count = len(records)
        self.out.notes.append(
            "📸 Сохранил фото прогресса" + (f" ({count} шт.)" if count > 1 else "")
        )

    def delete_record(self, action: DeleteRecord):
        model = {
            "weight": WeightEntry,
            "measurement": Measurement,
            "progress_photo": ProgressPhoto,
        }[action.entity]
        record = self.owned(model, action.record_id, ENTITY_NAMES[action.entity])
        if action.entity == "weight":
            what = f"вес {views.n(record.weight_kg, 1)} кг за {record.measured_on:%d.%m}"
        elif action.entity == "measurement":
            what = (
                f"замер «{MEASUREMENTS[record.kind][0].lower()}» {views.n(record.value, 1)} "
                f"за {record.measured_on:%d.%m}"
            )
        else:
            what = f"фото прогресса за {record.taken_on:%d.%m}"
        self.ask(
            "delete_record", {"entity": action.entity, "record_id": record.id}, f"Удалить {what}?"
        )

    # Memory and settings

    def save_note(self, action: SaveNote):
        note = notes.create(self.db, self.user, action.text, action.meal_type, "ai")
        when = notes.label(note, zone(self.tz_name))
        self.out.notes.append(f"📝 Заметка {when}: {note.text}")

    def remember(self, action: Remember):
        fact = memory.add(self.db, self.user.id, action.category, action.text, "ai")
        self.out.notes.append(f"📝 Запомнил: {fact.text}")
        self.out.created.append(["memory", fact.id])

    def update_memory(self, action: UpdateMemory):
        fact = self.owned(MemoryFact, action.memory_id, "факт")
        text = " ".join(action.text.split())[:500]
        if not text:
            raise DomainError("пустой факт")
        fact.text = text
        self.out.notes.append(f"📝 Обновил в памяти: {text}")

    def forget(self, action: Forget):
        fact = self.owned(MemoryFact, action.memory_id, "факт")
        self.out.notes.append(f"🧹 Забыл: {fact.text}")
        self.db.delete(fact)

    def update_profile(self, action: UpdateProfile):
        changes = action.changes
        profile = self.user.profile
        done = []

        def number(value, low, high, label):
            if not low <= value <= high:
                raise DomainError(f"{label}: значение вне диапазона {low}–{high}")
            return value

        if changes.sex:
            profile.sex = changes.sex
            done.append("пол")
        if changes.birth_date:
            try:
                born = date.fromisoformat(changes.birth_date)
            except ValueError:
                raise DomainError("дата рождения в формате ГГГГ-ММ-ДД") from None
            if not date(1900, 1, 1) < born < local_today(zone(self.tz_name)):
                raise DomainError("проверьте дату рождения")
            profile.birth_date = born
            done.append("дата рождения")
        if changes.height_cm is not None:
            profile.height_cm = number(changes.height_cm, 100, 250, "рост")
            done.append(f"рост {views.n(profile.height_cm)} см")
        if changes.activity:
            profile.activity = changes.activity
            done.append("активность")
        if changes.goal:
            profile.goal = changes.goal
            done.append("цель")
        if changes.target_weight_kg is not None:
            profile.target_weight_kg = number(changes.target_weight_kg, 30, 300, "целевой вес")
            done.append(f"целевой вес {views.n(profile.target_weight_kg, 1)} кг")
        # The assistant may not set a target below a safe floor (see the prompt).
        floor = 1500 if (changes.sex or profile.sex) == "male" else 1200
        for name, low, high, label in (
            ("kcal_target", floor, 6000, "ккал"),
            ("protein_target", 0, 500, "белок"),
            ("fat_target", 0, 400, "жиры"),
            ("carbs_target", 0, 1000, "углеводы"),
        ):
            value = getattr(changes, name)
            if value is not None:
                setattr(profile, name, int(number(value, low, high, label)))
                done.append(f"{label} {value}")
        if changes.timezone:
            if not valid_zone(changes.timezone):
                raise DomainError("неизвестный часовой пояс")
            profile.timezone = changes.timezone
            self.tz_name = changes.timezone
            for item in self.db.query(Reminder).filter(Reminder.user_id == self.user.id):
                reminders.reschedule(item, self.tz_name)
            done.append(f"часовой пояс {changes.timezone}")
        if done:
            self.out.notes.append("⚙️ Обновил профиль: " + ", ".join(done))

    def set_reminder(self, action: SetReminder):
        at = reminders.parse_time(action.time)
        days = sorted({day for day in action.days if 1 <= day <= 7})
        if not days:
            raise DomainError("не указаны дни напоминания")
        text = (action.text or "").strip()[:300] or None
        if action.reminder_kind == "custom" and not text:
            raise DomainError("нет текста напоминания")
        existing = None
        if action.reminder_kind != "custom":
            existing = (
                self.db.query(Reminder)
                .filter(Reminder.user_id == self.user.id, Reminder.kind == action.reminder_kind)
                .order_by(Reminder.id)
                .first()
            )
        reminder = existing or Reminder(user_id=self.user.id, kind=action.reminder_kind)
        every = min(max(action.every_weeks or 1, 1), 4)
        if every != (reminder.every_weeks or 1):
            reminder.anchor_on = None
        reminder.time = f"{at:%H:%M}"
        reminder.days = days
        reminder.every_weeks = every
        reminder.text = text
        reminder.enabled = True
        reminders.reschedule(reminder, self.tz_name)
        if not existing:
            self.db.add(reminder)
            self.db.flush()
            self.out.created.append(["reminder", reminder.id])
        self.out.notes.append(f"⏰ Напоминание: {reminders.describe(reminder)}")

    def save_product(self, action: SaveProduct):
        values = ProductIn(
            name=action.name.strip()[:200],
            brand=(action.brand or "").strip()[:120] or None,
            kcal=action.kcal,
            protein=action.protein,
            fat=action.fat,
            carbs=action.carbs,
            portion_name=(action.portion_name or "").strip()[:60] or None,
            portion_grams=action.portion_grams or None,
            package_grams=action.package_grams or None,
            comment=(action.comment or "").strip()[:1000] or None,
        ).model_dump()
        if action.product_id:
            product = self.owned(Product, action.product_id, "продукт")
        else:
            product = product_store.by_name(self.db, self.user.id, values["name"])
        created = product is None
        product = product_store.save(self.db, self.user.id, values, product)
        if action.use_photos and self.photos:
            product_store.attach(self.db, product, self.photos)
            self.photos = []
        verb = "Сохранил продукт" if created else "Обновил продукт"
        self.out.notes.append(f"🏷 {verb} {product_store.describe(product)}")
        if created:
            self.out.created.append(["product", product.id])

    def delete_product(self, action: DeleteProduct):
        product = self.owned(Product, action.product_id, "продукт")
        self.ask("delete_product", {"product_id": product.id}, f"Удалить продукт «{product.name}»?")

    def delete_reminder(self, action: DeleteReminder):
        reminder = self.owned(Reminder, action.reminder_id, "напоминание")
        self.out.notes.append(f"🔕 Удалил напоминание: {reminders.describe(reminder)}")
        self.db.delete(reminder)


# Pending actions and undo (run when the person presses a button)

UNDO_MODELS = {
    "product": Product,
    "weight": WeightEntry,
    "measurement": Measurement,
    "progress_photo": ProgressPhoto,
    "memory": MemoryFact,
    "reminder": Reminder,
}


def execute_pending(db: Session, user: User, action: PendingAction, choice: str = "y") -> str:
    """Runs a confirmed action; returns what was done."""
    payload = action.payload
    if action.kind.startswith("replace_"):
        return daily.apply(db, user, action, choice)
    if action.kind in ("edit_meal", "restore_meal", "update_meal"):
        meal = db.get(Meal, payload["meal_id"])
        if not meal or meal.user_id != user.id:
            raise DomainError("Запись уже удалена")
        if action.kind == "restore_meal":
            meal_edits.restore(meal, payload)
            return f"↩️ Вернул как было: «{meal.title}», {views.n(meal.kcal)} ккал"
        if action.kind == "edit_meal":
            if meal_edits.fingerprint(meal) != payload["before"]:
                raise DomainError("Запись уже изменилась. Напишите правку еще раз")
            meal_edits.apply(meal, meal_edits.Plan.load(payload["plan"]), user)
        else:  # proposed before item-by-item edits
            executor = Executor(db, user, [], meal.ai_model, meal.id)
            executor.apply_estimate(meal, MealEstimate.model_validate(payload["meal"]))
        return f"✅ Исправлено: «{meal.title}», {views.n(meal.kcal)} ккал"
    if action.kind == "delete_meal":
        meal = db.get(Meal, payload["meal_id"])
        if not meal or meal.user_id != user.id:
            raise DomainError("Запись уже удалена")
        nutrition.delete(db, meal)
        return f"🗑 Удалено: «{meal.title}»"
    if action.kind == "delete_product":
        product = db.get(Product, payload["product_id"])
        if not product or product.user_id != user.id:
            raise DomainError("Продукт уже удален")
        product_store.delete(db, product)
        return f"🗑 Продукт «{product.name}» удален"
    if action.kind == "update_weight":
        entry = db.get(WeightEntry, payload["weight_id"])
        if not entry or entry.user_id != user.id:
            raise DomainError("Запись уже удалена")
        entry.weight_kg = round(payload["weight_kg"], 2)
        return f"✅ Вес за {entry.measured_on:%d.%m}: {views.n(entry.weight_kg, 1)} кг"
    if action.kind == "delete_record":
        model = UNDO_MODELS[payload["entity"]]
        record = db.get(model, payload["record_id"])
        if not record or record.user_id != user.id:
            raise DomainError("Запись уже удалена")
        if isinstance(record, ProgressPhoto):
            progress.delete_photo(db, record)
        else:
            db.delete(record)
        return "🗑 Удалено"
    if action.kind == "undo":
        removed = 0
        for entity, record_id in payload["items"]:
            record = db.get(UNDO_MODELS[entity], record_id)
            if not record or record.user_id != user.id:
                continue
            if isinstance(record, ProgressPhoto):
                progress.delete_photo(db, record)
            elif isinstance(record, Product):
                product_store.delete(db, record)
            else:
                db.delete(record)
            removed += 1
        return "↩️ Отменено" if removed else "Уже нечего отменять"
    raise DomainError("Неизвестное действие")
