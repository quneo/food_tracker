from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, NotFound
from app.core.timeutil import from_local, local_day, local_today, to_local, zone
from app.database import utcnow
from app.media import service as media
from app.media.models import Media
from app.media.storage import Storage
from app.progress.models import MEASUREMENTS, Measurement, ProgressPhoto, WeightEntry
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


# Progress photos


def photo_out(db: Session, photo: ProgressPhoto) -> dict:
    nearest = db.scalars(
        select(WeightEntry).where(
            WeightEntry.user_id == photo.user_id,
            WeightEntry.measured_on >= photo.taken_on - timedelta(days=7),
            WeightEntry.measured_on <= photo.taken_on + timedelta(days=7),
        )
    ).all()
    nearest.sort(key=lambda entry: abs((entry.measured_on - photo.taken_on).days))
    return {
        "id": photo.id,
        "media_id": photo.media_id,
        "taken_on": photo.taken_on,
        "pose": photo.pose,
        "note": photo.note,
        "width": photo.media.width,
        "height": photo.media.height,
        "weight_kg": nearest[0].weight_kg if nearest else None,
    }


def photos(db: Session, user_id: int) -> list[ProgressPhoto]:
    return list(
        db.scalars(
            select(ProgressPhoto)
            .where(ProgressPhoto.user_id == user_id)
            .order_by(ProgressPhoto.taken_on.desc(), ProgressPhoto.id.desc())
        )
    )


def owned_photo(db: Session, photo_id: int, user_id: int) -> ProgressPhoto:
    return _owned(db, ProgressPhoto, photo_id, user_id)


def make_progress_photo(
    db: Session,
    user: User,
    item: Media,
    taken_on: date | None = None,
    pose: str = "front",
    note: str | None = None,
) -> ProgressPhoto:
    item.kind = "body"
    item.meal_id = None
    photo = ProgressPhoto(
        user_id=user.id,
        media_id=item.id,
        taken_on=taken_on or local_today(_tz(user)),
        pose=pose,
        note=note,
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


def delete_photo(db: Session, photo: ProgressPhoto):
    item = photo.media
    db.delete(photo)
    db.flush()
    media.drop(db, [item])
