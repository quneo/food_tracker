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
  n:t:<id>:<b|l|d|s|x>  weigh note for a meal (x = soon)  n:x:<id>  delete a note
  n:go:<id>   log the meal from a note now (opens a session)
"""

from datetime import date
from html import escape

from app.chat.outbox import view
from app.config import get_settings
from app.core.timeutil import to_local, zone
from app.notes import service as notes
from app.notes.models import WeighNote
from app.nutrition.models import Meal

MEAL_TYPES = {"breakfast": "Завтрак", "lunch": "Обед", "dinner": "Ужин", "snack": "Перекус"}
MEAL_ICONS = {"breakfast": "🍳", "lunch": "🍲", "dinner": "🍽", "snack": "🍏"}
TYPE_CODES = {"b": "breakfast", "l": "lunch", "d": "dinner", "s": "snack"}
NOTE_TARGETS = [
    ("🍳 Завтрак", "b"),
    ("🍲 Обед", "l"),
    ("🍽 Ужин", "d"),
    ("🍏 Перекус", "s"),
    ("⏱ 3 часа", "x"),
]
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


def day_line(eaten: dict, targets: dict | None, label: str = "За день") -> list[str]:
    """ "За день: 1748 из 2300 ккал", a bar under it, then protein, fat and carbs."""
    targets = targets or {}
    kcal, target = eaten["kcal"], targets.get("kcal")
    if target:
        left = target - kcal
        tail = f"осталось {n(left)}" if left >= 0 else f"больше нормы на {n(-left)}"
        lines = [
            f"{label}: <b>{n(kcal)}</b> из {target} ккал",
            f"{progress_bar(kcal / target)} {round(kcal / target * 100)}% · {tail}",
        ]
    else:
        lines = [f"{label}: <b>{n(kcal)}</b> ккал"]

    def macro(name: str, key: str) -> str:
        goal = targets.get(key)
        return f"{name} {n(eaten[key])}" + (f"/{goal}" if goal else "")

    lines.append(" · ".join([macro("Б", "protein"), macro("Ж", "fat"), macro("У", "carbs")]))
    return lines


def meal_text(
    meal: Meal,
    tz_name: str,
    day_total: dict | None = None,
    targets: dict | None = None,
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
        # A draft is not counted yet: show the day as it will be once it is saved.
        draft = meal.status == "draft"
        total = {
            key: value + (getattr(meal, key) if draft else 0) for key, value in day_total.items()
        }
        lines += ["", *day_line(total, targets, "С этим за день" if draft else "За день")]
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
    meal: Meal, tz_name: str, day_total=None, targets=None, deleting=False, changes=None
) -> dict:
    return view(meal_text(meal, tz_name, day_total, targets, changes), meal_buttons(meal, deleting))


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
        *day_line(totals, targets, "Съедено"),
        "",
    ]
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


def note_line(note: WeighNote, tz) -> str:
    """ "📝 на обед, сегодня: 130 грудка / 150 рис" for lists."""
    text = note.text.replace("\n", " / ")
    text = text if len(text) <= 80 else text[:80] + "…"
    return f"📝 {escape(notes.label(note, tz))}: {escape(text)}"


def note_view(note: WeighNote, tz_name: str, head: str = "Заметка") -> dict:
    """A weigh note: what it is for, the grams, and buttons to move it to another meal,
    log it now or drop it."""
    tz = zone(tz_name)
    due = notes.is_due(note)
    hint = (
        "Пора есть: «▶️ Учесть сейчас» посчитает и запишет. В сессии можно и словами: "
        "«обед по заметке», или пришлите фото."
        if due
        else "Всплывет к этому приему, в сессии ассистент учтет граммы сам. Другой прием — "
        "кнопками ниже."
    )
    text = (
        f"📝 <b>{escape(head)}</b> {escape(notes.label(note, tz))}\n\n"
        f"{escape(note.text)}\n\n<i>{hint}</i>"
    )
    current = next(
        (code for code, kind in {**TYPE_CODES, "x": None}.items() if kind == note.meal_type), "x"
    )
    targets = [
        button(("✓ " if code == current else "") + label, f"n:t:{note.id}:{code}")
        for label, code in NOTE_TARGETS
    ]
    return view(
        text,
        [
            targets[:3],
            targets[3:],
            [
                button("▶️ Учесть сейчас", f"n:go:{note.id}", "success"),
                button("🗑", f"n:x:{note.id}"),
            ],
        ],
    )
