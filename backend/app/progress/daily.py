"""Once a day in the bot: a weight, each measurement and the progress photos of a day are
recorded once. A second one for the same day is not saved: the person is asked whether
to replace what is there (or, for photos, to add to them). The site has no such limit."""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat import views
from app.chat.models import PendingAction
from app.chat.outbox import view
from app.core.exceptions import DomainError
from app.core.timeutil import from_local, local_today, to_local, zone
from app.database import utcnow
from app.media.models import Media
from app.progress import service as progress
from app.progress.models import MEASUREMENTS, Measurement, ProgressEntry, ProgressPhoto, WeightEntry
from app.users.models import User

ASK_FOR = timedelta(hours=24)


def _day(user: User, local: datetime | None) -> date:
    tz = zone(user.profile.timezone)
    return to_local(from_local(local, tz), tz).date() if local else local_today(tz)


def _which(user: User, day: date) -> str:
    return "сегодня" if day == local_today(zone(user.profile.timezone)) else f"за {day:%d.%m}"


def _ask(db: Session, user: User, kind: str, payload: dict, summary: str) -> PendingAction:
    action = PendingAction(
        user_id=user.id,
        kind=kind,
        payload=payload,
        summary=summary,
        expires_at=utcnow() + ASK_FOR,
    )
    db.add(action)
    db.flush()
    return action


def _unit(kind: str) -> str:
    return "%" if MEASUREMENTS[kind][1] == "%" else " см"


def weight(
    db: Session, user: User, value: float, local: datetime | None = None
) -> tuple[WeightEntry | None, PendingAction | None]:
    """-> (the saved weight, or the question about replacing the day's one)."""
    day = _day(user, local)
    existing = db.scalar(
        select(WeightEntry)
        .where(WeightEntry.user_id == user.id, WeightEntry.measured_on == day)
        .order_by(WeightEntry.measured_at.desc())
    )
    if not existing:
        return progress.add_weight(db, user, value, local, source="bot"), None
    if not 20 <= value <= 400:
        raise DomainError("Вес должен быть от 20 до 400 кг")
    when = to_local(existing.measured_at, zone(user.profile.timezone))
    summary = (
        f"Вес {_which(user, day)} уже записан: {views.n(existing.weight_kg, 1)} кг в "
        f"{when:%H:%M}. Заменить на {views.n(value, 1)} кг?"
    )
    return None, _ask(
        db, user, "replace_weight", {"weight_id": existing.id, "weight_kg": value}, summary
    )


def measurements(
    db: Session, user: User, values: dict[str, float], local: datetime | None = None
) -> tuple[list[Measurement], PendingAction | None]:
    """New kinds are saved; kinds already measured that day wait for "replace"."""
    day = _day(user, local)
    existing = {
        entry.kind: entry
        for entry in db.scalars(
            select(Measurement)
            .where(Measurement.user_id == user.id, Measurement.measured_on == day)
            .order_by(Measurement.measured_at)
        )
    }
    saved = [
        progress.add_measurement(db, user, kind, value, local, source="bot")
        for kind, value in values.items()
        if kind not in existing
    ]
    repeat = {kind: value for kind, value in values.items() if kind in existing}
    if not repeat:
        return saved, None
    changes = ", ".join(
        f"{MEASUREMENTS[kind][0].lower()} {views.n(existing[kind].value, 1)} → "
        f"{views.n(value, 1)}{_unit(kind)}"
        for kind, value in repeat.items()
    )
    summary = f"Уже записано {_which(user, day)}: заменить {changes}?"
    items = [[existing[kind].id, value] for kind, value in repeat.items()]
    return saved, _ask(db, user, "replace_measurements", {"items": items}, summary)


def progress_photos(
    db: Session, user: User, photos: list[Media], note: str | None, first_pose: str = "front"
) -> tuple[list[ProgressPhoto], PendingAction | None]:
    """Today's photos join an empty day; a day that has photos asks first."""
    day = local_today(zone(user.profile.timezone))
    entry = db.scalar(
        select(ProgressEntry).where(ProgressEntry.user_id == user.id, ProgressEntry.taken_on == day)
    )
    if not entry or not entry.photos:
        poses = progress.poses_for(len(photos), first_pose)
        saved = [
            progress.make_progress_photo(db, user, item, pose=pose, note=note)
            for item, pose in zip(photos, poses, strict=True)
        ]
        return saved, None
    count = len(entry.photos)
    summary = f"Фото прогресса за сегодня уже есть ({count}). Заменить их новыми?"
    payload = {"media_ids": [item.id for item in photos], "note": note, "pose": first_pose}
    return [], _ask(db, user, "replace_progress", payload, summary)


def replace_view(action: PendingAction, add: bool = False) -> dict:
    """The question with plain answers: replace, (add,) keep."""
    rows = [[views.button("🔁 Заменить", f"a:y:{action.id}")]]
    if add:
        rows[0].append(views.button("➕ Добавить к ним", f"a:add:{action.id}"))
    rows.append([views.button("Оставить как было", f"a:n:{action.id}")])
    return view(f"❓ {action.summary}", rows)


def apply(db: Session, user: User, action: PendingAction, choice: str) -> str:
    """Runs a confirmed replacement. -> what was done."""
    payload = action.payload
    if action.kind == "replace_weight":
        entry = db.get(WeightEntry, payload["weight_id"])
        if not entry or entry.user_id != user.id:
            entry = progress.add_weight(db, user, payload["weight_kg"], source="bot")
        entry.weight_kg = round(payload["weight_kg"], 2)
        entry.measured_at = utcnow()
        entry.source = "bot"
        return f"✅ Вес заменен: {views.n(entry.weight_kg, 1)} кг"
    if action.kind == "replace_measurements":
        done = []
        for entry_id, value in payload["items"]:
            entry = db.get(Measurement, entry_id)
            if not entry or entry.user_id != user.id:
                continue
            entry.value = round(value, 1)
            entry.measured_at = utcnow()
            done.append(
                f"{MEASUREMENTS[entry.kind][0].lower()} {views.n(entry.value, 1)}{_unit(entry.kind)}"
            )
        return "✅ Заменил: " + ", ".join(done) if done else "Замеров уже нет"
    if action.kind == "replace_progress":
        photos = [
            item
            for item in db.scalars(select(Media).where(Media.id.in_(payload["media_ids"])))
            if item.user_id == user.id and item.kind == "chat"
        ]
        if not photos:
            raise DomainError("Фото уже недоступны, пришлите их еще раз")
        day = local_today(zone(user.profile.timezone))
        entry = db.scalar(
            select(ProgressEntry).where(
                ProgressEntry.user_id == user.id, ProgressEntry.taken_on == day
            )
        )
        taken = [photo.pose for photo in entry.photos] if entry else []
        if choice == "y" and entry:
            for photo in list(entry.photos):
                progress.delete_photo(db, photo)
            taken = []
        free = [pose for pose in progress.UPLOAD_POSES if pose not in taken]
        poses = progress.poses_for(len(photos), payload.get("pose") or "front")
        if taken:
            poses = [free[i] if i < len(free) else "other" for i in range(len(photos))]
        for item, pose in zip(photos, poses, strict=True):
            progress.make_progress_photo(db, user, item, pose=pose, note=payload.get("note"))
        return "📸 Фото заменены" if choice == "y" else "📸 Добавил к сегодняшним фото"
    raise DomainError("Неизвестное действие")
