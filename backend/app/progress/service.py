from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import DomainError, NotFound
from app.core.timeutil import from_local, local_day, local_today, to_local, zone
from app.database import utcnow
from app.media import service as media
from app.media.models import Media
from app.media.storage import Storage
from app.progress.models import (
    MEASUREMENTS,
    Measurement,
    ProgressEntry,
    ProgressPhoto,
    WeightEntry,
)
from app.users.models import User


def _tz(user: User):
    return zone(user.profile.timezone)


def _when(user: User, local: datetime | None) -> tuple[datetime, date]:
    tz = _tz(user)
    at = from_local(local, tz) if local else utcnow()
    if at > utcnow() + timedelta(hours=1):
        raise DomainError("Дата в будущем")
    return at, local_day(at, tz)


def _owned(db: Session, model, record_id: int, user_id: int):
    record = db.get(model, record_id)
    if not record or record.user_id != user_id:
        raise NotFound()
    return record


# Weight


def weight_out(entry: WeightEntry, user: User) -> dict:
    return {
        "id": entry.id,
        "weight_kg": entry.weight_kg,
        "measured_at": to_local(entry.measured_at, _tz(user)).isoformat(timespec="minutes"),
        "measured_on": entry.measured_on,
        "note": entry.note,
        "source": entry.source,
    }


def add_weight(
    db: Session,
    user: User,
    weight_kg: float,
    local: datetime | None = None,
    note: str | None = None,
    source: str = "web",
) -> WeightEntry:
    if not 20 <= weight_kg <= 400:
        raise DomainError("Вес должен быть от 20 до 400 кг")
    at, day = _when(user, local)
    entry = WeightEntry(
        user_id=user.id,
        weight_kg=round(weight_kg, 2),
        measured_at=at,
        measured_on=day,
        note=note,
        source=source,
    )
    db.add(entry)
    db.flush()
    return entry


def weights(db: Session, user_id: int, start: date | None = None, end: date | None = None):
    query = select(WeightEntry).where(WeightEntry.user_id == user_id)
    if start:
        query = query.where(WeightEntry.measured_on >= start)
    if end:
        query = query.where(WeightEntry.measured_on <= end)
    return list(db.scalars(query.order_by(WeightEntry.measured_at.desc())))


def latest_weight(db: Session, user_id: int) -> WeightEntry | None:
    return db.scalar(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id)
        .order_by(WeightEntry.measured_at.desc())
        .limit(1)
    )


def owned_weight(db: Session, entry_id: int, user_id: int) -> WeightEntry:
    return _owned(db, WeightEntry, entry_id, user_id)


def update_weight(db: Session, user: User, entry: WeightEntry, data) -> WeightEntry:
    entry.weight_kg = round(data.weight_kg, 2)
    if data.measured_at:
        entry.measured_at, entry.measured_on = _when(user, data.measured_at)
    entry.note = data.note
    db.flush()
    return entry


def weight_change(db: Session, user: User, days: int) -> float | None:
    """Change of the latest weight against the last one at least `days` earlier."""
    latest = latest_weight(db, user.id)
    if not latest:
        return None
    before = db.scalar(
        select(WeightEntry)
        .where(
            WeightEntry.user_id == user.id,
            WeightEntry.measured_on <= latest.measured_on - timedelta(days=days),
        )
        .order_by(WeightEntry.measured_at.desc())
        .limit(1)
    )
    return round(latest.weight_kg - before.weight_kg, 1) if before else None


# Measurements


def measurement_out(entry: Measurement, user: User) -> dict:
    return {
        "id": entry.id,
        "kind": entry.kind,
        "value": entry.value,
        "unit": entry.unit,
        "measured_at": to_local(entry.measured_at, _tz(user)).isoformat(timespec="minutes"),
        "measured_on": entry.measured_on,
        "note": entry.note,
        "source": entry.source,
    }


def add_measurement(
    db: Session,
    user: User,
    kind: str,
    value: float,
    local: datetime | None = None,
    note: str | None = None,
    source: str = "web",
) -> Measurement:
    if kind not in MEASUREMENTS:
        raise DomainError("Неизвестный замер")
    limit = 75 if kind == "body_fat" else 300
    if not 0 < value <= limit:
        raise DomainError("Проверьте значение замера")
    at, day = _when(user, local)
    entry = Measurement(
        user_id=user.id,
        kind=kind,
        value=round(value, 1),
        measured_at=at,
        measured_on=day,
        note=note,
        source=source,
    )
    db.add(entry)
    db.flush()
    return entry


def measurements(db: Session, user_id: int, start: date | None = None, end: date | None = None):
    query = select(Measurement).where(Measurement.user_id == user_id)
    if start:
        query = query.where(Measurement.measured_on >= start)
    if end:
        query = query.where(Measurement.measured_on <= end)
    return list(db.scalars(query.order_by(Measurement.measured_at.desc())))


def owned_measurement(db: Session, entry_id: int, user_id: int) -> Measurement:
    return _owned(db, Measurement, entry_id, user_id)


def update_measurement(db: Session, user: User, entry: Measurement, data) -> Measurement:
    limit = 75 if data.kind == "body_fat" else 300
    if not 0 < data.value <= limit:
        raise DomainError("Проверьте значение замера")
    entry.kind = data.kind
    entry.value = round(data.value, 1)
    if data.measured_at:
        entry.measured_at, entry.measured_on = _when(user, data.measured_at)
    entry.note = data.note
    db.flush()
    return entry


def add_measurements(
    db: Session,
    user: User,
    values: dict[str, float],
    local: datetime | None = None,
    note: str | None = None,
) -> list[Measurement]:
    """One sitting with the tape: several measurements at the same moment."""
    if not values:
        raise DomainError("Впишите хотя бы один замер")
    return [add_measurement(db, user, kind, value, local, note) for kind, value in values.items()]


# Progress photos: one entry per day holds that day's photos from every angle.

POSE_ORDER = {"front": 0, "side": 1, "back": 2, "other": 3}
# Several photos at once without angles: front first, then back, then side.
UPLOAD_POSES = ("front", "back", "side")


def poses_for(count: int, first: str = "front") -> list[str]:
    if count == 1:
        return [first]
    order = [first] + [pose for pose in UPLOAD_POSES if pose != first]
    return [order[i] if i < len(order) else "other" for i in range(count)]


def nearest_weight(db: Session, user_id: int, day: date) -> float | None:
    """The weight closest to the day, within a week."""
    nearest = db.scalars(
        select(WeightEntry).where(
            WeightEntry.user_id == user_id,
            WeightEntry.measured_on >= day - timedelta(days=7),
            WeightEntry.measured_on <= day + timedelta(days=7),
        )
    ).all()
    nearest.sort(key=lambda entry: abs((entry.measured_on - day).days))
    return nearest[0].weight_kg if nearest else None


def photo_out(db: Session, photo: ProgressPhoto, weight: float | None = None) -> dict:
    return {
        "id": photo.id,
        "entry_id": photo.entry_id,
        "media_id": photo.media_id,
        "taken_on": photo.taken_on,
        "pose": photo.pose,
        "note": photo.entry.note,
        "width": photo.media.width,
        "height": photo.media.height,
        "weight_kg": weight
        if weight is not None
        else nearest_weight(db, photo.user_id, photo.taken_on),
    }


def entry_out(db: Session, entry: ProgressEntry) -> dict:
    weight = nearest_weight(db, entry.user_id, entry.taken_on)
    photos = sorted(entry.photos, key=lambda photo: (POSE_ORDER[photo.pose], photo.id))
    return {
        "id": entry.id,
        "taken_on": entry.taken_on,
        "note": entry.note,
        "weight_kg": weight,
        "photos": [photo_out(db, photo, weight) for photo in photos],
    }


def photos(db: Session, user_id: int) -> list[ProgressPhoto]:
    return list(
        db.scalars(
            select(ProgressPhoto)
            .where(ProgressPhoto.user_id == user_id)
            .order_by(ProgressPhoto.taken_on.desc(), ProgressPhoto.id.desc())
        )
    )


def entries(db: Session, user_id: int) -> list[ProgressEntry]:
    return list(
        db.scalars(
            select(ProgressEntry)
            .where(ProgressEntry.user_id == user_id)
            .options(selectinload(ProgressEntry.photos))
            .order_by(ProgressEntry.taken_on.desc())
        )
    )


def owned_photo(db: Session, photo_id: int, user_id: int) -> ProgressPhoto:
    return _owned(db, ProgressPhoto, photo_id, user_id)


def owned_entry(db: Session, entry_id: int, user_id: int) -> ProgressEntry:
    return _owned(db, ProgressEntry, entry_id, user_id)


def entry_for(db: Session, user_id: int, day: date) -> ProgressEntry:
    entry = db.scalar(
        select(ProgressEntry).where(ProgressEntry.user_id == user_id, ProgressEntry.taken_on == day)
    )
    if not entry:
        entry = ProgressEntry(user_id=user_id, taken_on=day)
        db.add(entry)
        db.flush()
    return entry


def make_progress_photo(
    db: Session,
    user: User,
    item: Media,
    taken_on: date | None = None,
    pose: str = "front",
    note: str | None = None,
) -> ProgressPhoto:
    """Files a photo into the entry of its day (made if it is the first one)."""
    item.kind = "body"
    item.meal_id = None
    day = taken_on or local_today(_tz(user))
    entry = entry_for(db, user.id, day)
    if note and not entry.note:
        entry.note = note
    photo = ProgressPhoto(
        user_id=user.id, entry_id=entry.id, media_id=item.id, taken_on=day, pose=pose
    )
    db.add(photo)
    db.flush()
    return photo


def upload_photo(
    db: Session,
    storage: Storage,
    user: User,
    data: bytes,
    taken_on: date | None,
    pose: str,
    note: str | None,
) -> ProgressPhoto:
    if taken_on and taken_on > local_today(_tz(user)):
        raise DomainError("Дата в будущем")
    item = media.save_photo(db, storage, user.id, data, "body")
    return make_progress_photo(db, user, item, taken_on, pose, note)


def _drop_if_empty(db: Session, entry: ProgressEntry):
    left = db.scalar(select(func.count(ProgressPhoto.id)).where(ProgressPhoto.entry_id == entry.id))
    if not left:
        db.delete(entry)


def move_photo(db: Session, user: User, photo: ProgressPhoto, day: date) -> ProgressPhoto:
    """To another day: the photo joins that day's entry."""
    if day > local_today(_tz(user)):
        raise DomainError("Дата в будущем")
    if day == photo.taken_on:
        return photo
    old = photo.entry
    photo.entry = entry_for(db, user.id, day)
    photo.taken_on = day
    db.flush()
    _drop_if_empty(db, old)
    db.flush()
    return photo


def update_entry(
    db: Session, user: User, entry: ProgressEntry, day: date | None, note: str | None, fields
) -> ProgressEntry:
    """A new day merges the entry into the one already there, if any."""
    if "note" in fields:
        entry.note = (note or "").strip() or None
    if day and day != entry.taken_on:
        if day > local_today(_tz(user)):
            raise DomainError("Дата в будущем")
        other = db.scalar(
            select(ProgressEntry).where(
                ProgressEntry.user_id == user.id, ProgressEntry.taken_on == day
            )
        )
        if other:
            for photo in list(entry.photos):
                photo.entry = other
                photo.taken_on = day
            other.note = other.note or entry.note
            db.flush()
            db.delete(entry)
            entry = other
        else:
            entry.taken_on = day
            for photo in entry.photos:
                photo.taken_on = day
    db.flush()
    return entry


def delete_entry(db: Session, entry: ProgressEntry):
    items = [photo.media for photo in entry.photos]
    for photo in list(entry.photos):
        db.delete(photo)
    db.delete(entry)
    db.flush()
    media.drop(db, items)


def delete_photo(db: Session, photo: ProgressPhoto):
    """One photo; the entry goes too when it was the last one."""
    item, entry = photo.media, photo.entry
    db.delete(photo)
    db.flush()
    _drop_if_empty(db, entry)
    db.flush()
    media.drop(db, [item])
