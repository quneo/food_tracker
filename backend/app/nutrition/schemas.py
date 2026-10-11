from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MealType = Literal["breakfast", "lunch", "dinner", "snack"]
Confidence = Literal["low", "medium", "high"]
GramsSource = Literal["estimated", "stated", "label"]


class MealItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    grams: float | None = Field(default=None, gt=0, le=5000)
    grams_source: GramsSource = "stated"
    kcal: float = Field(ge=0, le=10000)
    protein: float = Field(default=0, ge=0, le=1000)
    fat: float = Field(default=0, ge=0, le=1000)
    carbs: float = Field(default=0, ge=0, le=2000)
    confidence: Confidence | None = None
    note: str | None = Field(default=None, max_length=300)


class MealIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    meal_type: MealType | None = None
    # Local wall time in the person's time zone, "2026-10-11T13:30".
    eaten_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)
    items: list[MealItemIn] = Field(min_length=1, max_length=40)


class MealPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    meal_type: MealType | None = None
    eaten_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)
    items: list[MealItemIn] | None = Field(default=None, min_length=1, max_length=40)


class MealItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    grams: float | None
    grams_source: GramsSource
    kcal: float
    protein: float
    fat: float
    carbs: float
    confidence: Confidence | None
    note: str | None


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    width: int
    height: int


class MealOut(BaseModel):
    id: int
    status: Literal["draft", "confirmed"]
    meal_type: MealType | None
    title: str
    eaten_at: str  # local ISO time with offset
    eaten_on: date
    note: str | None
    source: str
    kcal: float
    protein: float
    fat: float
    carbs: float
    estimated_by: str
    confidence: Confidence | None
    kcal_low: float | None
    kcal_high: float | None
    assumptions: list[str]
    items: list[MealItemOut]
    photos: list[PhotoOut]
    created_at: str


class Totals(BaseModel):
    kcal: float = 0
    protein: float = 0
    fat: float = 0
    carbs: float = 0


class Targets(BaseModel):
    kcal: int | None
    protein: int | None
    fat: int | None
    carbs: int | None


class DaySummary(BaseModel):
    day: date
    totals: Totals
    targets: Targets
    meals: list[MealOut]
    drafts: int
