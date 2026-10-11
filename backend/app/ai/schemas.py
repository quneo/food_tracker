"""What the assistant must answer: a reply plus a list of proposed actions.

The JSON Schema of TurnResult goes to Codex as --output-schema, so field descriptions are
instructions too. Nothing here touches the database: app.ai.actions checks every action
against the person's data before anything is changed."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["low", "medium", "high"]
MealType = Literal["breakfast", "lunch", "dinner", "snack"]
MemoryCategory = Literal[
    "goal", "preference", "dislike", "allergy", "health", "habit", "food", "other"
]
LocalTime = Annotated[
    str | None,
    Field(description="Local time 'YYYY-MM-DDTHH:MM' if the user named a day or time; null = now."),
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FoodItem(Strict):
    name: str = Field(description="Food in Russian as people say it: 'Гречка отварная'.")
    grams: float = Field(description="Best estimate of the edible weight in grams.")
    grams_source: Literal["estimated", "stated", "label"] = Field(
        description="estimated = you guessed it; stated = the user gave the weight or "
        "exact amount; label = read from a package label."
    )
    kcal: float
    protein: float = Field(description="Grams.")
    fat: float = Field(description="Grams.")
    carbs: float = Field(description="Grams.")
    confidence: Confidence
    note: str | None = Field(
        description="Short assumption for this item ('жарено, ~1 ст. л. масла учтено') or null."
    )


class MealEstimate(Strict):
    title: str = Field(description="Short dish name in Russian: 'Курица с рисом и салатом'.")
    meal_type: MealType | None = Field(
        description="If clear from the user's words or the time; else null."
    )
    eaten_at: LocalTime
    items: list[FoodItem] = Field(description="Every component separately, sauces and oil too.")
    kcal_low: float = Field(description="Plausible lower bound of the meal's total kcal.")
    kcal_high: float = Field(description="Plausible upper bound of the meal's total kcal.")
    confidence: Confidence
    assumptions: list[str] = Field(
        description="Key assumptions in Russian, short (portion size, cooking method, hidden "
        "fat). Empty if the user gave exact data."
    )


class CreateMeal(Strict):
    kind: Literal["create_meal"]
    meal: MealEstimate
    use_photos: bool = Field(description="Attach the photos of the current message to this meal.")


class UpdateMeal(Strict):
    kind: Literal["update_meal"]
    meal_id: int = Field(description="Id of a meal shown in the context.")
    meal: MealEstimate = Field(description="The complete corrected meal, all items.")


class DeleteMeal(Strict):
    kind: Literal["delete_meal"]
    meal_id: int


class LogWeight(Strict):
    kind: Literal["log_weight"]
    weight_kg: float
    measured_at: LocalTime


class UpdateWeight(Strict):
    kind: Literal["update_weight"]
    weight_id: int
    weight_kg: float


class MeasurementValue(Strict):
    kind: Literal["waist", "hips", "chest", "neck", "arm", "thigh", "calf", "body_fat"]
    value: float = Field(description="Centimetres; percent for body_fat.")


class LogMeasurements(Strict):
    kind: Literal["log_measurements"]
    values: list[MeasurementValue]
    measured_at: LocalTime


class SaveProgressPhoto(Strict):
    kind: Literal["save_progress_photo"]
    pose: Literal["front", "side", "back", "other"]
    note: str | None


class DeleteRecord(Strict):
    kind: Literal["delete_record"]
    entity: Literal["weight", "measurement", "progress_photo"]
    record_id: int


class Remember(Strict):
    kind: Literal["remember"]
    category: MemoryCategory
    text: str = Field(
        description="One self-contained fact in Russian, third person: 'Не ест свинину'."
    )


class UpdateMemory(Strict):
    kind: Literal["update_memory"]
    memory_id: int
    text: str


class Forget(Strict):
    kind: Literal["forget"]
    memory_id: int


class ProfileChanges(Strict):
    sex: Literal["male", "female"] | None
    birth_date: str | None = Field(description="YYYY-MM-DD")
    height_cm: float | None
    activity: Literal["sedentary", "light", "moderate", "high", "very_high"] | None
    goal: Literal["lose", "maintain", "gain"] | None
    target_weight_kg: float | None
    kcal_target: int | None
    protein_target: int | None
    fat_target: int | None
    carbs_target: int | None
    timezone: str | None = Field(description="IANA name, e.g. Europe/Moscow")


class UpdateProfile(Strict):
    kind: Literal["update_profile"]
    changes: ProfileChanges = Field(description="Only what the user asked to change; null = keep.")


class SetReminder(Strict):
    kind: Literal["set_reminder"]
    reminder_kind: Literal["meal", "weight", "photo", "custom"]
    time: str = Field(description="Local 'HH:MM'.")
    days: list[int] = Field(description="ISO weekdays, 1 = Monday ... 7 = Sunday.")
    text: str | None = Field(description="Reminder text for custom reminders, else null.")


class DeleteReminder(Strict):
    kind: Literal["delete_reminder"]
    reminder_id: int


Action = Annotated[
    CreateMeal
    | UpdateMeal
    | DeleteMeal
    | LogWeight
    | UpdateWeight
    | LogMeasurements
    | SaveProgressPhoto
    | DeleteRecord
    | Remember
    | UpdateMemory
    | Forget
    | UpdateProfile
    | SetReminder
    | DeleteReminder,
    Field(discriminator="kind"),
]


class TurnResult(Strict):
    reply: str = Field(
        description="Message to the user in Russian, plain text, 1-4 short sentences unless "
        "they asked for detail. Do not repeat meal items or numbers: the app shows a card."
    )
    actions: list[Action]
