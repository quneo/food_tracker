"""What the assistant gets to see with a message: a compact text snapshot of the person's
data, picked for this message. Records carry ids like [meal 12] so actions can refer to them."""

import re
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import memory
from app.ai.models import MemoryFact
from app.chat.models import ChatMessage, ChatSession, ChatState
from app.core.timeutil import local_now, to_local, zone
from app.nutrition.models import Meal, MealItem
from app.nutrition.targets import age, suggest
from app.progress.models import MEASUREMENTS, Measurement, ProgressPhoto, WeightEntry
from app.reminders.models import Reminder
from app.reminders.service import describe
from app.users.models import User

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MEAL_TYPES = {"breakfast": "завтрак", "lunch": "обед", "dinner": "ужин", "snack": "перекус"}
SEX = {"male": "мужской", "female": "женский"}
GOALS = {"lose": "снижение веса", "maintain": "поддержание веса", "gain": "набор массы"}
ACTIVITY = {
    "sedentary": "сидячий образ жизни",
    "light": "низкая активность",
    "moderate": "умеренная активность",
    "high": "высокая активность",
    "very_high": "очень высокая активность",
}
DAY_WORDS = {"сегодня": 0, "вчера": 1, "позавчера": 2}
DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b")
HISTORY_DAYS = 60
# A question about eating overall brings the last two weeks into the context.
STATS_WORDS = re.compile(
    r"анализ|разбер|разбор|рацион|за недел|за месяц|в среднем|итог|статистик|тенденц|динамик"
    r"|как я пита|что улучш|что не так",
    re.IGNORECASE,
)
RECENT_MESSAGES = 12
# A session is shown whole, up to this many of its latest messages.
SESSION_MESSAGES = 40


def n(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "?"
    rounded = round(value, digits)
    return str(int(rounded)) if digits == 0 or rounded == int(rounded) else str(rounded)


def macros(record) -> str:
    return f"{n(record.kcal)} ккал, Б {n(record.protein)} / Ж {n(record.fat)} / У {n(record.carbs)}"


class Context:
    def __init__(
        self,
        db: Session,
        user: User,
        message: ChatMessage,
        review_days: int | None = None,
        batch: list[ChatMessage] | None = None,
        session: ChatSession | None = None,
        photo_notes: list[str] | None = None,
    ):
        self.review_days = review_days
        self.db = db
        self.user = user
        self.message = message
        # The new messages answered at once (several when sent in a quick row).
        self.batch = batch or [message]
        self.session = session
        self.photo_notes = photo_notes or []
        self.text = "\n".join(item.text for item in self.batch if item.text)
        self.photos = sum(item.photos for item in self.batch)
        self.tz = zone(user.profile.timezone)
        self.now = local_now(self.tz)
        self.today = self.now.date()
        self.state = db.get(ChatState, user.id)

    def build(self) -> str:
        parts = [
            self.section_now(),
            self.section_profile(),
            self.section_today(),
            self.section_drafts(),
            self.section_mentioned_days(),
            self.section_similar_meals(),
            self.section_frequent_foods(),
            self.section_body(),
            self.section_products(),
            self.section_stats(),
            self.section_reminders(),
            self.section_memory(),
            self.section_conversation(),
            self.section_message(),
        ]
        return "\n\n".join(part for part in parts if part)

    # Sections

    def section_now(self) -> str:
        weekday = WEEKDAYS[self.now.weekday()]
        return (
            f"## Сейчас\n{self.now:%Y-%m-%d %H:%M}, {weekday}, "
            f"часовой пояс {self.user.profile.timezone}"
        )

    def section_profile(self) -> str:
        profile = self.user.profile
        lines = [f"Имя: {self.user.first_name or 'не указано'}"]
        if profile.sex:
            lines.append(f"Пол: {SEX[profile.sex]}")
        if profile.birth_date:
            lines.append(f"Возраст: {age(profile.birth_date, self.today)}")
        if profile.height_cm:
            lines.append(f"Рост: {n(profile.height_cm)} см")
        weight = self.db.scalar(
            select(WeightEntry)
            .where(WeightEntry.user_id == self.user.id)
            .order_by(WeightEntry.measured_at.desc())
            .limit(1)
        )
        if profile.height_cm and weight:
            bmi = weight.weight_kg / (profile.height_cm / 100) ** 2
            lines.append(f"ИМТ: {n(bmi, 1)}")
        if weight:
            lines.append(f"Последний вес: {n(weight.weight_kg, 1)} кг ({weight.measured_on:%d.%m})")
        if profile.goal:
            goal = GOALS[profile.goal]
            if profile.target_weight_kg:
                goal += f", целевой вес {n(profile.target_weight_kg, 1)} кг"
            lines.append(f"Цель: {goal}")
        if profile.activity:
            lines.append(f"Активность: {ACTIVITY[profile.activity]}")
        targets = [
            f"{label} {value}"
            for label, value in (
                ("ккал", profile.kcal_target),
                ("Б", profile.protein_target),
                ("Ж", profile.fat_target),
                ("У", profile.carbs_target),
            )
            if value
        ]
        lines.append("Норма в день: " + (", ".join(targets) if targets else "не задана"))
        estimate = suggest(
            profile.sex,
            profile.birth_date,
            profile.height_cm,
            weight.weight_kg if weight else None,
            profile.activity,
            profile.goal,
            self.today,
        )
        if estimate:
            lines.append(
                f"Расчет по Миффлину — Сан Жеору: обмен {estimate['bmr']}, расход "
                f"{estimate['tdee']} ккал; под цель {estimate['kcal']} ккал, "
                f"Б {estimate['protein']} / Ж {estimate['fat']} / У {estimate['carbs']}"
            )
        lines.append(
            "Новые приемы пищи: "
            + (
                "сохраняются сразу"
                if profile.auto_confirm_meals
                else "приходят черновиком, человек подтверждает"
            )
        )
        if profile.about:
            lines.append(f"О себе: {profile.about}")
        return "## Профиль\n" + "\n".join(lines)

    def meal_line(self, meal: Meal, with_day: bool = False) -> str:
        local = to_local(meal.eaten_at, self.tz)
        when = f"{local:%d.%m %H:%M}" if with_day else f"{local:%H:%M}"
        kind = MEAL_TYPES.get(meal.meal_type or "", "")
        status = "черновик" if meal.status == "draft" else "сохранен"
        return f"- [meal {meal.id}] {when} {kind}: {meal.title}; {macros(meal)}; {status}"

    def meal_details(self, meal: Meal) -> str:
        lines = [self.meal_line(meal, with_day=True)]
        for item in meal.items:
            grams = (
                f"~{n(item.grams)} г (оценка)"
                if item.grams_source == "estimated"
                else f"{n(item.grams)} г"
            )
            lines.append(f"    · [item {item.id}] {item.name}, {grams}: {macros(item)}")
        if meal.assumptions:
            lines.append("    допущения: " + "; ".join(meal.assumptions))
        if meal.note:
            lines.append(f"    комментарий: {meal.note}")
        return "\n".join(lines)

    def meals_on(self, day: date) -> list[Meal]:
        return list(
            self.db.scalars(
                select(Meal)
                .where(Meal.user_id == self.user.id, Meal.eaten_on == day)
                .order_by(Meal.eaten_at)
            )
        )

    def section_today(self) -> str:
        meals = self.meals_on(self.today)
        saved = [meal for meal in meals if meal.status == "confirmed"]
        total = {f: sum(getattr(m, f) for m in saved) for f in ("kcal", "protein", "fat", "carbs")}
        target = self.user.profile.kcal_target
        share = f" ({round(total['kcal'] / target * 100)}% нормы)" if target else ""
        lines = [
            f"Сохранено: {n(total['kcal'])} ккал{share}, Б {n(total['protein'])} / "
            f"Ж {n(total['fat'])} / У {n(total['carbs'])}"
        ]
        profile = self.user.profile
        left = [
            f"{label} {n(value - total[field])}"
            if value >= total[field]
            else f"{label} перебор {n(total[field] - value)}"
            for label, field, value in (
                ("ккал", "kcal", profile.kcal_target),
                ("Б", "protein", profile.protein_target),
                ("Ж", "fat", profile.fat_target),
                ("У", "carbs", profile.carbs_target),
            )
            if value
        ]
        if left:
            lines.append("До нормы осталось: " + ", ".join(left))
        # Today's meals with their items: a correction changes items by id.
        lines += [self.meal_details(meal) for meal in meals] or ["- записей нет"]
        text = self.text.lower()
        for back, word in ((1, "вчера"), (2, "позавчера")):
            day = self.today - timedelta(days=back)
            recent = self.meals_on(day)
            if not recent:
                continue
            lines.append(f"{word.capitalize()}, {day:%d.%m}:")
            named = word in (text if back == 2 else text.replace("позавчера", ""))
            lines += [
                self.meal_details(meal) if named else self.meal_line(meal, with_day=True)
                for meal in recent
            ]
        return "## Питание сегодня\n" + "\n".join(lines)

    def section_drafts(self) -> str:
        focus = self.state.focus_meal_id if self.state else None
        drafts = list(
            self.db.scalars(
                select(Meal)
                .where(
                    Meal.user_id == self.user.id,
                    Meal.status == "draft",
                    Meal.eaten_on >= self.today - timedelta(days=3),
                    Meal.eaten_on != self.today,  # today's are shown in full above
                )
                .order_by(Meal.eaten_at)
            )
        )
        parts = []
        if focus:
            meal = self.db.get(Meal, focus)
            if meal and meal.user_id == self.user.id:
                parts.append(
                    "## Запись, которую пользователь нажал «Исправить»\n"
                    "Сообщение скорее всего исправляет ее (edit_meal с этим id).\n"
                    + self.meal_details(meal)
                )
                drafts = [draft for draft in drafts if draft.id != meal.id]
        if drafts:
            parts.append(
                "## Черновики (ждут подтверждения, еще не учтены в итогах)\n"
                + "\n".join(self.meal_details(meal) for meal in drafts)
            )
        return "\n\n".join(parts)

    def mentioned_days(self) -> list[date]:
        text = self.text.lower()
        days = set()
        for word, back in DAY_WORDS.items():
            if word in text and back > 0:
                days.add(self.today - timedelta(days=back))
        for index, name in enumerate(WEEKDAYS):
            if name[:4] in text:
                back = (self.today.weekday() - index) % 7 or 7
                days.add(self.today - timedelta(days=back))
        for day, month, year in DATE.findall(text):
            try:
                value = date(int(year) if len(year) == 4 else self.today.year, int(month), int(day))
            except ValueError:
                continue
            if value <= self.today:
                days.add(value)
        return sorted(day for day in days if day < self.today - timedelta(days=2))

    def section_mentioned_days(self) -> str:
        lines = []
        for day in self.mentioned_days()[:3]:
            meals = self.meals_on(day)
            lines.append(f"{day:%d.%m.%Y}:")
            lines += [self.meal_details(meal) for meal in meals] or ["- записей нет"]
        return "## Упомянутые дни\n" + "\n".join(lines) if lines else ""

    def section_similar_meals(self) -> str:
        words = memory.stems(self.text)
        if not words:
            return ""
        since = self.today - timedelta(days=HISTORY_DAYS)
        meals = self.db.scalars(
            select(Meal)
            .where(
                Meal.user_id == self.user.id,
                Meal.status == "confirmed",
                Meal.eaten_on >= since,
                Meal.eaten_on < self.today - timedelta(days=2),
            )
            .order_by(Meal.eaten_at.desc())
            .limit(400)
        ).all()
        scored = []
        for meal in meals:
            names = " ".join([meal.title] + [item.name for item in meal.items])
            overlap = len(words & memory.stems(names))
            if overlap:
                scored.append((overlap, meal.eaten_at, meal))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        if not scored:
            return ""
        return "## Похожие приемы пищи из истории\n" + "\n".join(
            self.meal_details(meal) for _, _, meal in scored[:5]
        )

    def section_frequent_foods(self) -> str:
        since = self.today - timedelta(days=HISTORY_DAYS)
        items = self.db.scalars(
            select(MealItem)
            .join(Meal)
            .where(
                Meal.user_id == self.user.id,
                Meal.status == "confirmed",
                Meal.eaten_on >= since,
            )
        ).all()
        groups: dict[str, list[MealItem]] = defaultdict(list)
        for item in items:
            groups[item.name.strip().lower()].append(item)
        common = sorted(groups.items(), key=lambda pair: len(pair[1]), reverse=True)[:15]
        lines = []
        for _name, group in common:
            if len(group) < 2:
                break
            weighed = [item for item in group if item.grams]
            grams = sum(item.grams for item in weighed) / len(weighed) if weighed else None
            density = (
                sum(item.kcal for item in weighed) / sum(item.grams for item in weighed) * 100
                if weighed and sum(item.grams for item in weighed)
                else None
            )
            lines.append(
                f"- {group[0].name}: {len(group)} раз, обычно ~{n(grams)} г, "
                f"~{n(density)} ккал/100 г"
            )
        if not lines:
            return ""
        return (
            "## Частые продукты пользователя (за 60 дней, его же сохраненные оценки)\n"
            + "\n".join(lines)
        )

    def section_body(self) -> str:
        lines = []
        weights = self.db.scalars(
            select(WeightEntry)
            .where(WeightEntry.user_id == self.user.id)
            .order_by(WeightEntry.measured_at.desc())
            .limit(10)
        ).all()
        if weights:
            lines.append(
                "Вес: "
                + "; ".join(
                    f"[weight {entry.id}] {entry.measured_on:%d.%m} {n(entry.weight_kg, 1)} кг"
                    for entry in weights
                )
            )
        entries = self.db.scalars(
            select(Measurement)
            .where(Measurement.user_id == self.user.id)
            .order_by(Measurement.measured_at.desc())
            .limit(16)
        ).all()
        if entries:
            lines.append(
                "Замеры: "
                + "; ".join(
                    f"[measurement {entry.id}] {entry.measured_on:%d.%m} "
                    f"{MEASUREMENTS[entry.kind][0].lower()} {n(entry.value, 1)} {entry.unit}"
                    for entry in entries
                )
            )
        photos = self.db.scalars(
            select(ProgressPhoto)
            .where(ProgressPhoto.user_id == self.user.id)
            .order_by(ProgressPhoto.taken_on.desc())
            .limit(4)
        ).all()
        if photos:
            lines.append(
                "Фото прогресса: "
                + "; ".join(
                    f"[progress_photo {photo.id}] {photo.taken_on:%d.%m} {photo.pose}"
                    for photo in photos
                )
            )
        return "## Тело и прогресс\n" + "\n".join(lines) if lines else ""

    def section_reminders(self) -> str:
        reminders = self.db.scalars(
            select(Reminder).where(Reminder.user_id == self.user.id).order_by(Reminder.id)
        ).all()
        lines = [
            f"- [reminder {item.id}] {describe(item)}{'' if item.enabled else ' (выключено)'}"
            for item in reminders
        ]
        return "## Напоминания\n" + "\n".join(lines) if lines else ""

    def section_memory(self) -> str:
        facts: list[MemoryFact] = memory.relevant(self.db, self.user.id, self.text)
        if not facts:
            return "## Память о пользователе\n- пока пусто"
        return "## Память о пользователе\n" + "\n".join(
            f"- [memory {fact.id}] ({fact.category}) {fact.text}" for fact in facts
        )

    def section_conversation(self) -> str:
        if self.session:
            return self.section_session()
        since = self.now.replace(tzinfo=None) - timedelta(hours=12)
        query = (
            select(ChatMessage)
            .where(ChatMessage.user_id == self.user.id, ChatMessage.id < self.message.id)
            .order_by(ChatMessage.id.desc())
            .limit(RECENT_MESSAGES)
        )
        messages = list(reversed(self.db.scalars(query).all()))
        start = self.state.context_from if self.state and self.state.context_from else None
        lines = []
        for message in messages:
            local = to_local(message.created_at, self.tz)
            if local.replace(tzinfo=None) < since or (start and message.created_at < start):
                continue
            who = "Пользователь" if message.role == "user" else "Ассистент"
            photos = f" [фото: {message.photos}]" if message.photos else ""
            text = message.text if len(message.text) <= 600 else message.text[:600] + "…"
            lines.append(f"[{local:%H:%M}] {who}{photos}: {text}")
        return "## Недавний диалог\n" + "\n".join(lines) if lines else ""

    def section_session(self) -> str:
        """Everything said in this session before the new messages."""
        messages = self.db.scalars(
            select(ChatMessage)
            .where(
                ChatMessage.session_id == self.session.id,
                ChatMessage.id < self.batch[0].id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(SESSION_MESSAGES)
        ).all()
        started = to_local(self.session.started_at, self.tz)
        lines = []
        for message in reversed(messages):
            local = to_local(message.created_at, self.tz)
            who = "Пользователь" if message.role == "user" else "Ассистент"
            photos = f" [фото: {message.photos}]" if message.photos else ""
            text = message.text if len(message.text) <= 1600 else message.text[:1600] + "…"
            lines.append(f"[{local:%H:%M}] {who}{photos}: {text}")
        body = "\n".join(lines) if lines else "- это начало сессии"
        return f"## Сессия (начата в {started:%H:%M})\n{body}"

    def section_products(self) -> str:
        from app.nutrition.products import list_products

        products = list_products(self.db, self.user.id)
        if not products:
            return ""
        if len(products) > 60:
            words = memory.stems(self.text)
            matching = [
                product
                for product in products
                if words & memory.stems(f"{product.name} {product.brand or ''}")
            ]
            products = matching + [p for p in products[:40] if p not in matching]
        lines = []
        for product in products:
            line = (
                f"- [product {product.id}] {product.name}"
                + (f" ({product.brand})" if product.brand else "")
                + f": на 100 г {n(product.kcal)} ккал, Б {n(product.protein, 1)} / "
                f"Ж {n(product.fat, 1)} / У {n(product.carbs, 1)}"
            )
            if product.portion_grams:
                portion = product.portion_name or "порция"
                line += f"; {portion} {n(product.portion_grams)} г"
            if product.package_grams:
                line += f"; упаковка {n(product.package_grams)} г"
            if product.comment:
                line += f"; {product.comment}"
            lines.append(line)
        return "## Мои продукты (значения с этикеток)\n" + "\n".join(lines)

    def wants_stats(self) -> bool:
        return bool(STATS_WORDS.search(self.text))

    def section_stats(self) -> str:
        """Day by day numbers for a review, or when the person asks about their eating."""
        from app.analytics.service import daily, report

        # A short week by default, so advice and meal comments see the trend.
        days = self.review_days or (14 if self.wants_stats() else 7)
        start = self.today - timedelta(days=days - 1)
        rows = daily(self.db, self.user, start, self.today)
        meals = self.db.scalars(
            select(Meal).where(
                Meal.user_id == self.user.id,
                Meal.status == "confirmed",
                Meal.eaten_on >= start,
            )
        ).all()
        times: dict[date, list[str]] = defaultdict(list)
        for meal in meals:
            times[meal.eaten_on].append(f"{to_local(meal.eaten_at, self.tz):%H:%M}")
        target = self.user.profile.kcal_target
        status = {"complete": "полный", "partial": "неполный", "empty": "нет записей"}
        lines = []
        for row in rows:
            day = row["day"]
            label = f"{day:%d.%m} {WEEKDAYS[day.weekday()][:2]}"
            if row["status"] == "empty":
                lines.append(f"- {label}: нет записей")
                continue
            share = f" ({round(row['kcal'] / target * 100)}%)" if target else ""
            eaten = sorted(times.get(day, []))
            span = f", {eaten[0]}–{eaten[-1]}" if eaten else ""
            lines.append(
                f"- {label}: {n(row['kcal'])} ккал{share}, Б {n(row['protein'])} / "
                f"Ж {n(row['fat'])} / У {n(row['carbs'])}, приемов {row['meals']}{span}, "
                f"{status[row['status']]}"
            )
        summary = report(self.db, self.user, start, self.today)
        averages = summary["averages"]
        extra = [
            f"Дней с записями {summary['logged_days']} из {summary['days']}, полных "
            f"{summary['complete_days']}. Средние ниже — по полным дням.",
        ]
        if averages["kcal"] is not None:
            extra.append(
                f"В среднем: {n(averages['kcal'])} ккал, Б {n(averages['protein'])} / "
                f"Ж {n(averages['fat'])} / У {n(averages['carbs'])}"
            )
        if summary["days_within_target"] is not None and summary["counted_days"]:
            extra.append(
                f"Дней в пределах ±10% от нормы: {summary['days_within_target']} из "
                f"{summary['counted_days']}"
            )
        if summary["weight"]:
            weight = summary["weight"]
            extra.append(
                f"Вес: {n(weight['first'], 1)} → {n(weight['last'], 1)} кг "
                f"({'+' if weight['change'] > 0 else ''}{n(weight['change'], 1)})"
            )
        if summary["top_foods"]:
            extra.append(
                "Чаще всего: "
                + ", ".join(f"{item['name']} ({item['count']})" for item in summary["top_foods"])
            )
        return (
            f"## Статистика за {days} дн. ({start:%d.%m}–{self.today:%d.%m})\n"
            + "\n".join(lines)
            + "\n"
            + "\n".join(extra)
        )

    def section_message(self) -> str:
        hints = []
        if self.photo_notes:
            hints.append(
                "Приложенные фото по порядку:\n" + "\n".join(f"- {n}" for n in self.photo_notes)
            )
        elif self.photos:
            hints.append(f"К сообщению приложено фото: {self.photos} шт.")
        if self.state and self.state.mode == "progress":
            hints.append("Пользователь включил режим «фото прогресса»: фото — это фото тела.")
        hint = ("\n" + "\n".join(hints)) if hints else ""
        if len(self.batch) == 1:
            text = self.text.strip() or "(без текста)"
            return f"## Новое сообщение пользователя{hint}\n<<<\n{text}\n>>>"
        parts = []
        for item in self.batch:
            local = to_local(item.created_at, self.tz)
            photos = f" [фото: {item.photos}]" if item.photos else ""
            parts.append(f"[{local:%H:%M}]{photos} {item.text.strip() or '(без текста)'}")
        body = "\n".join(parts)
        return (
            f"## Новые сообщения пользователя ({len(self.batch)}, ответь на все вместе){hint}"
            f"\n<<<\n{body}\n>>>"
        )


def build(
    db: Session,
    user: User,
    message: ChatMessage,
    review_days: int | None = None,
    batch: list[ChatMessage] | None = None,
    session: ChatSession | None = None,
    photo_notes: list[str] | None = None,
) -> str:
    return Context(db, user, message, review_days, batch, session, photo_notes).build()
