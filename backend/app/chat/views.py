"""Telegram messages (HTML + inline buttons) built on the server, so the bot stays a thin
transport and every rule lives next to the data.

Callback data (64 bytes max):
  m:ok:<id>  save a draft            m:t:<id>:<b|l|d|s>  set meal type
  m:e:<id>   fix (next message)      m:x:<id>  delete a draft
  m:d:<id>   ask to delete saved     m:dd:<id> delete saved    m:v:<id> show again
  a:y:<id> / a:n:<id>  answer a pending action      u:<id>  undo
  l:y:<code> / l:n:<code>  web sign-in             r:off:<id>  reminder off
  s:go:<msg>  start a session with a message sent outside one
  s:pr:<msg>  file that message's photos as progress   aw:x  cancel a number prompt
  rv:<days>   review the diet (opens a session)          h:help  how to use
  pin:reset / pin:keep  forgotten photo code           p:x  cancel /progress
"""

from datetime import date
from html import escape

from app.chat.outbox import view
from app.config import get_settings
from app.core.timeutil import to_local, zone
from app.nutrition.models import Meal

MEAL_TYPES = {"breakfast": "Завтрак", "lunch": "Обед", "dinner": "Ужин", "snack": "Перекус"}
TYPE_CODES = {"b": "breakfast", "l": "lunch", "d": "dinner", "s": "snack"}
CONFIDENCE = {"low": "низкая", "medium": "средняя", "high": "высокая"}
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]  # fmt: skip


def n(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "—"
    rounded = round(value, digits)
    if digits == 0 or rounded == int(rounded):
        return str(int(rounded))
    return str(rounded).replace(".", ",")


def day_name(day: date, today: date) -> str:
    if day == today:
        return "сегодня"
    if (today - day).days == 1:
        return "вчера"
    return f"{day.day} {MONTHS[day.month - 1]}"


def button(text: str, data: str) -> dict:
    return {"text": text, "data": data}


def site_button(text: str, path: str) -> dict | None:
    """Opens the diary. Over https it opens inside Telegram as a Mini App, signed in by
    Telegram itself; only people who use the bot ever see these buttons."""
    base = get_settings().app_url
    if not base:
        return None
    key = "web_app" if base.startswith("https://") else "url"
    return {"text": text, key: f"{base}{path}"}


def grams(item) -> str:
    if item.grams is None:
        return ""
    return f"~{n(item.grams)} г" if item.grams_source == "estimated" else f"{n(item.grams)} г"


def meal_text(meal: Meal, tz_name: str, day_total: dict | None = None, target=None) -> str:
    tz = zone(tz_name)
    local = to_local(meal.eaten_at, tz)
    approx = "≈ " if meal.estimated_by == "ai" else ""
    kind = MEAL_TYPES.get(meal.meal_type or "", "Прием пищи")
    status = "черновик" if meal.status == "draft" else "сохранено ✅"
    when = f"{local:%H:%M}"
    if local.date() != to_local(meal.created_at, tz).date():
        when = f"{local:%d.%m} {when}"
    lines = [
        f"🍽 <b>{escape(meal.title)}</b>",
        f"{kind} · {when} · {status}",
        f"<b>{approx}{n(meal.kcal)} ккал</b>"
        + (
            f" ({n(meal.kcal_low)}–{n(meal.kcal_high)})"
            if meal.kcal_low is not None and meal.kcal_high is not None
            else ""
        )
        + f" · Б {n(meal.protein)} · Ж {n(meal.fat)} · У {n(meal.carbs)}",
        "",
    ]
    for item in meal.items:
        weight = grams(item)
        lines.append(
            f"• {escape(item.name)}{', ' + weight if weight else ''} — {n(item.kcal)} ккал"
        )
    if meal.ai_comment:
        lines += ["", f"💬 {escape(meal.ai_comment)}"]
    if meal.assumptions:
        lines += ["", "<i>Допущения: " + escape("; ".join(meal.assumptions)) + "</i>"]
    if meal.estimated_by == "ai" and meal.confidence:
        lines.append(f"<i>Уверенность оценки: {CONFIDENCE[meal.confidence]}</i>")
    if meal.note:
        lines.append(f"💬 {escape(meal.note)}")
    if day_total is not None:
        total = day_total["kcal"] + (meal.kcal if meal.status == "draft" else 0)
        prefix = "С этим за день" if meal.status == "draft" else "За день"
        goal = f" из {target}" if target else ""
        lines += ["", f"{prefix}: {n(total)}{goal} ккал"]
    return "\n".join(lines)


def meal_buttons(meal: Meal, deleting: bool = False) -> list:
    if deleting:
        return [[button("🗑 Да, удалить", f"m:dd:{meal.id}"), button("Отмена", f"m:v:{meal.id}")]]
    # One short row: the rest (meal type, time, grams) is fixed in words via "Fix".
    if meal.status == "draft":
        return [
            [
                button("✅ Сохранить", f"m:ok:{meal.id}"),
                button("✏️ Исправить", f"m:e:{meal.id}"),
                button("🗑", f"m:x:{meal.id}"),
            ]
        ]
    return [[button("✏️ Исправить", f"m:e:{meal.id}"), button("🗑 Удалить", f"m:d:{meal.id}")]]


def meal_view(meal: Meal, tz_name: str, day_total=None, target=None, deleting=False) -> dict:
    return view(meal_text(meal, tz_name, day_total, target), meal_buttons(meal, deleting))


def confirm_view(action_id: int, summary: str) -> dict:
    return view(
        f"❓ {escape(summary)}",
        [[button("✅ Да", f"a:y:{action_id}"), button("✖️ Нет", f"a:n:{action_id}")]],
    )


def progress_bar(share: float, width: int = 10) -> str:
    filled = max(0, min(width, round(share * width)))
    return "▓" * filled + "░" * (width - filled)


def today_view(summary: dict, today: date, weight=None, change=None) -> dict:
    totals, targets = summary["totals"], summary["targets"]
    lines = [
        f"📊 <b>{day_name(today, today).capitalize()}, {today.day} {MONTHS[today.month - 1]}</b>"
    ]
    if targets["kcal"]:
        left = targets["kcal"] - totals["kcal"]
        tail = f"осталось {n(left)}" if left >= 0 else f"больше нормы на {n(-left)}"
        lines.append(f"<b>{n(totals['kcal'])} из {targets['kcal']} ккал</b> · {tail}")
        lines.append(progress_bar(totals["kcal"] / targets["kcal"]))
    else:
        lines.append(f"<b>{n(totals['kcal'])} ккал</b>")

    def macro(label, key):
        goal = targets[key]
        return f"{label} {n(totals[key])}" + (f"/{goal}" if goal else "")

    lines.append(" · ".join([macro("Б", "protein"), macro("Ж", "fat"), macro("У", "carbs")]))
    lines.append("")
    meals = summary["meals"]
    if not meals:
        lines.append("Пока ничего не записано. Пришлите фото еды или опишите словами.")
    for meal in meals:
        kind = MEAL_TYPES.get(meal["meal_type"] or "", "Прием пищи")
        draft = " <i>(черновик)</i>" if meal["status"] == "draft" else ""
        lines.append(
            f"{kind} {meal['eaten_at'][11:16]} — {escape(meal['title'])}, "
            f"{n(meal['kcal'])} ккал{draft}"
        )
    if weight:
        delta = f" ({'+' if change > 0 else ''}{n(change, 1)} за неделю)" if change else ""
        lines += ["", f"⚖️ Вес: {n(weight.weight_kg, 1)} кг{delta}"]
    link = site_button("Открыть дневник", "/")
    return view("\n".join(lines), [[link]] if link else [])
