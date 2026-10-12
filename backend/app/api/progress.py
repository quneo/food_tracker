from datetime import date

from fastapi import APIRouter, BackgroundTasks, File, Form, Response, UploadFile

from app.api.deps import CurrentUser, Db, Files, purge_later
from app.progress import service
from app.progress.schemas import (
    EntryPatch,
    MeasurementIn,
    MeasurementOut,
    MeasurementsIn,
    PhotoPatch,
    Pose,
    ProgressEntryOut,
    ProgressPhotoOut,
    WeightIn,
    WeightOut,
)

router = APIRouter(tags=["progress"])


# Weight


@router.get("/weights", response_model=list[WeightOut])
def list_weights(user: CurrentUser, db: Db, start: date | None = None, end: date | None = None):
    return [service.weight_out(entry, user) for entry in service.weights(db, user.id, start, end)]


@router.post("/weights", response_model=WeightOut, status_code=201)
def add_weight(data: WeightIn, user: CurrentUser, db: Db):
    entry = service.add_weight(db, user, data.weight_kg, data.measured_at, data.note)
    db.commit()
    return service.weight_out(entry, user)


@router.put("/weights/{entry_id}", response_model=WeightOut)
def update_weight(entry_id: int, data: WeightIn, user: CurrentUser, db: Db):
    entry = service.owned_weight(db, entry_id, user.id)
    service.update_weight(db, user, entry, data)
    db.commit()
    return service.weight_out(entry, user)


@router.delete("/weights/{entry_id}", status_code=204)
def delete_weight(entry_id: int, user: CurrentUser, db: Db):
    db.delete(service.owned_weight(db, entry_id, user.id))
    db.commit()
    return Response(status_code=204)


# Measurements


@router.get("/measurements", response_model=list[MeasurementOut])
def list_measurements(
    user: CurrentUser, db: Db, start: date | None = None, end: date | None = None
):
    return [
        service.measurement_out(entry, user)
        for entry in service.measurements(db, user.id, start, end)
    ]


@router.post("/measurements", response_model=MeasurementOut, status_code=201)
def add_measurement(data: MeasurementIn, user: CurrentUser, db: Db):
    entry = service.add_measurement(db, user, data.kind, data.value, data.measured_at, data.note)
    db.commit()
    return service.measurement_out(entry, user)


@router.post("/measurements/batch", response_model=list[MeasurementOut], status_code=201)
def add_measurements(data: MeasurementsIn, user: CurrentUser, db: Db):
    entries = service.add_measurements(db, user, data.values, data.measured_at, data.note)
    db.commit()
    return [service.measurement_out(entry, user) for entry in entries]


@router.put("/measurements/{entry_id}", response_model=MeasurementOut)
def update_measurement(entry_id: int, data: MeasurementIn, user: CurrentUser, db: Db):
    entry = service.owned_measurement(db, entry_id, user.id)
    service.update_measurement(db, user, entry, data)
    db.commit()
    return service.measurement_out(entry, user)


@router.delete("/measurements/{entry_id}", status_code=204)
def delete_measurement(entry_id: int, user: CurrentUser, db: Db):
    db.delete(service.owned_measurement(db, entry_id, user.id))
    db.commit()
    return Response(status_code=204)


# Progress photos: entries by day, each with its photos


@router.get("/progress-entries", response_model=list[ProgressEntryOut])
def list_entries(user: CurrentUser, db: Db):
    return [service.entry_out(db, entry) for entry in service.entries(db, user.id)]


@router.patch("/progress-entries/{entry_id}", response_model=ProgressEntryOut)
def update_entry(entry_id: int, data: EntryPatch, user: CurrentUser, db: Db):
    entry = service.owned_entry(db, entry_id, user.id)
    entry = service.update_entry(db, user, entry, data.taken_on, data.note, data.model_fields_set)
    db.commit()
    return service.entry_out(db, entry)


@router.delete("/progress-entries/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int, user: CurrentUser, db: Db, files: Files, background: BackgroundTasks
):
    service.delete_entry(db, service.owned_entry(db, entry_id, user.id))
    db.commit()
    purge_later(background, db, files)
    return Response(status_code=204)


@router.get("/progress-photos", response_model=list[ProgressPhotoOut])
def list_photos(user: CurrentUser, db: Db):
    return [service.photo_out(db, photo) for photo in service.photos(db, user.id)]


@router.post("/progress-photos", response_model=ProgressPhotoOut, status_code=201)
def upload_photo(
    user: CurrentUser,
    db: Db,
    files: Files,
    photo: UploadFile = File(),
    taken_on: date | None = Form(default=None),
    pose: Pose = Form(default="front"),
    note: str | None = Form(default=None, max_length=300),
):
    record = service.upload_photo(db, files, user, photo.file.read(), taken_on, pose, note or None)
    db.commit()
    return service.photo_out(db, record)


@router.patch("/progress-photos/{photo_id}", response_model=ProgressPhotoOut)
def update_photo(photo_id: int, data: PhotoPatch, user: CurrentUser, db: Db):
    """Angle, or another day (the photo moves to that day's entry)."""
    photo = service.owned_photo(db, photo_id, user.id)
    if data.taken_on:
        service.move_photo(db, user, photo, data.taken_on)
    if data.pose:
        photo.pose = data.pose
    db.commit()
    return service.photo_out(db, photo)


@router.delete("/progress-photos/{photo_id}", status_code=204)
def delete_photo(
    photo_id: int, user: CurrentUser, db: Db, files: Files, background: BackgroundTasks
):
    service.delete_photo(db, service.owned_photo(db, photo_id, user.id))
    db.commit()
    purge_later(background, db, files)
    return Response(status_code=204)
