from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

MeasurementKind = Literal["waist", "hips", "chest", "neck", "arm", "thigh", "calf", "body_fat"]
Pose = Literal["front", "side", "back", "other"]


class WeightIn(BaseModel):
    weight_kg: float = Field(ge=20, le=400)
    measured_at: datetime | None = None  # local wall time; now when empty
    note: str | None = Field(default=None, max_length=300)


class WeightOut(BaseModel):
    id: int
    weight_kg: float
    measured_at: str
    measured_on: date
    note: str | None
    source: str


class MeasurementIn(BaseModel):
    kind: MeasurementKind
    value: float = Field(gt=0, le=300)
    measured_at: datetime | None = None
    note: str | None = Field(default=None, max_length=300)


class MeasurementOut(BaseModel):
    id: int
    kind: str
    value: float
    unit: str
    measured_at: str
    measured_on: date
    note: str | None
    source: str


class PhotoPatch(BaseModel):
    taken_on: date | None = None
    pose: Pose | None = None
    note: str | None = Field(default=None, max_length=300)


class ProgressPhotoOut(BaseModel):
    id: int
    media_id: int
    taken_on: date
    pose: Pose
    note: str | None
    width: int
    height: int
    weight_kg: float | None  # the weight closest to the photo's day, within a week
