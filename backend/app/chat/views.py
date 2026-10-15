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
MEAL_ICONS = {"breakfast": "🍳", "lunch": "🍲", "dinner": "🍽", "snack": "🍏"}
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


def button(text: str, data: str, style: str | None = None) -> dict:
    """style: "success" (green), "danger" (red) or "primary" (blue); None = plain."""
    result = {"text": text, "data": data}
    if style:
        result["style"] = style
    return result


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


def day_line(eaten: float, target: int | None, label: str = "За день") -> list[str]:
    """ "За день: 1748 из 2300 ккал" and a bar under it."""
    if not target:
        return [f"{label}: {n(eaten)} ккал"]
    left = target - eaten
    tail = f"осталось {n(left)}" if left >= 0 else f"больше нормы на {n(-left)}"
    return [
        f"{label}: <b>{n(eaten)}</b> из {target} ккал",
        f"{progress_bar(eaten / target)} {round(eaten / target * 100)}% · {tail}",
    ]


def meal_text(
    meal: Meal,
    tz_name: str,
    day_total: dict | None = None,
    target=None,
    changes: list[str] | None = None,
) -> str:
    """The meal card: the numbers first, the items, what changed, the remark; how it was
    estimated is folded away."""
    tz = zone(tz_name)
    local = to_local(meal.eaten_at, tz)
    approx = "≈ " if meal.estimated_by == "ai" else ""
    kind = MEAL_TYPES.get(meal.meal_type or "", "Прием пищи")
    status = "📝 черновик" if meal.status == "draft" else "сохранено ✅"
    when = f"{local:%H:%M}"
    if local.date() != to_local(meal.created_at, tz).date():
        when = f"{local:%d.%m} {when}"
    lines = [
        f"{MEAL_ICONS.get(meal.meal_type or '', '🍽')} <b>{escape(meal.title)}</b>",
        f"{kind} · {when} · {status}",
        "",
        f"<b>{approx}{n(meal.kcal)} ккал</b> · Б {n(meal.protein)} · Ж {n(meal.fat)} · "
        f"У {n(meal.carbs)}",
        "",
    ]
    for item in meal.items:
        weight = grams(item)
        lines.append(
            f"• {escape(item.name)}{', ' + weight if weight else ''} — {n(item.kcal)} ккал"
        )
    if changes:
        lines += ["", "✏️ <b>Что изменилось</b>", *(escape(line) for line in changes)]
    if meal.ai_comment:
        lines += ["", f"💬 <i>{escape(meal.ai_comment)}</i>"]
    if meal.note:
        lines += ["", f"📝 {escape(meal.note)}"]
    details = []
    if meal.assumptions:
        details.append("Как считал: " + escape("; ".join(meal.assumptions)))
    if meal.estimated_by == "ai":
        honest = []
        if meal.kcal_low is not None and meal.kcal_high is not None:
            honest.append(f"на деле от {n(meal.kcal_low)} до {n(meal.kcal_high)} ккал")
        if meal.confidence:
            honest.append(f"уверенность {CONFIDENCE[meal.confidence]}")
        if honest:
            details.append("Оценка: " + ", ".join(honest))
    if details:
        lines += ["", "<blockquote expandable>" + "\n".join(details) + "</blockquote>"]
    if day_total is not None:
        draft = meal.status == "draft"
        total = day_total["kcal"] + (meal.kcal if draft else 0)
        lines += ["", *day_line(total, target, "С этим за день" if draft else "За день")]
    return "\n".join(lines)


def meal_buttons(meal: Meal, deleting: bool = False) -> list:
    if deleting:
        return [
            [
                button("🗑 Да, удалить", f"m:dd:{meal.id}", "danger"),
                button("Отмена", f"m:v:{meal.id}"),
            ]
        ]
    # One short row: the rest (meal type, time, grams) is fixed in words via "Fix".
    if meal.status == "draft":
        return [
            [
                button("✅ Сохранить", f"m:ok:{meal.id}", "success"),
                button("✏️ Исправить", f"m:e:{meal.id}"),
                button("🗑", f"m:x:{meal.id}"),
            ]
        ]
    return [[button("✏️ Исправить", f"m:e:{meal.id}"), button("🗑 Удалить", f"m:d:{meal.id}")]]


def meal_view(
    meal: Meal, tz_name: str, day_total=None, target=None, deleting=False, changes=None
) -> dict:
    return view(meal_text(meal, tz_name, day_total, target, changes), meal_buttons(meal, deleting))


def confirm_view(action_id: int, summary: str, danger: bool = False) -> dict:
    yes = "🗑 Да, удалить" if danger else "✅ Да"
    return view(
        f"❓ {escape(summary)}",
        [
            [
                button(yes, f"a:y:{action_id}", "danger" if danger else "success"),
                button("✖️ Нет", f"a:n:{action_id}"),
            ]
        ],
    )


def progress_bar(share: float, width: int = 10) -> str:
    filled = max(0, min(width, round(share * width)))
    return "▰" * filled + "▱" * (width - filled)


def today_view(summary: dict, today: date, weight=None, change=None) -> dict:
    totals, targets = summary["totals"], summary["targets"]
    lines = [
        f"📊 <b>{day_name(today, today).capitalize()}, {today.day} {MONTHS[today.month - 1]}</b>",
        "",
        *day_line(totals["kcal"], targets["kcal"], "Съедено"),
    ]

    def macro(label, key):
        goal = targets[key]
        return f"{label} {n(totals[key])}" + (f"/{goal}" if goal else "")

    lines.append(" · ".join([macro("Б", "protein"), macro("Ж", "fat"), macro("У", "carbs")]))
    lines.append("")
    meals = summary["meals"]
    if not meals:
        lines.append("Пока ничего не записано. Начните сессию и пришлите фото еды.")
    for meal in meals:
        icon = MEAL_ICONS.get(meal["meal_type"] or "", "🍽")
        draft = " <i>черновик</i>" if meal["status"] == "draft" else ""
        lines.append(
            f"{icon} {meal['eaten_at'][11:16]} {escape(meal['title'])} — "
            f"<b>{n(meal['kcal'])}</b>{draft}"
        )
    if weight:
        sign = "+" if change and change > 0 else ""
        delta = f", {sign}{n(change, 1).replace('-', '−')} за неделю" if change else ""
        lines += ["", f"⚖️ {n(weight.weight_kg, 1)} кг{delta}"]
    link = site_button("Открыть дневник", "/")
    return view("\n".join(lines), [[link]] if link else [])
