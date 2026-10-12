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
    product_id: int | None = Field(
        description="Id of the user's saved product ([product N]) when this item is that "
        "product; the app then computes kcal and macros from its label and `grams`."
    )
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
    comment: str | None = Field(
        description="Your remark about this meal for the user, in Russian: one short sentence "
        "usually; 2-4 sentences when there is something worth saying. Practical, specific, "
        "friendly. Do not repeat the card's numbers."
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
    reminder_kind: Literal["meal", "weight", "photo", "measure", "review", "custom"]
    time: str = Field(description="Local 'HH:MM'.")
    days: list[int] = Field(description="ISO weekdays, 1 = Monday ... 7 = Sunday.")
    every_weeks: int | None = Field(
        description="Repeat every N weeks (2-4) on those days; null = every week."
    )
    text: str | None = Field(description="Reminder text for custom reminders, else null.")


class DeleteReminder(Strict):
    kind: Literal["delete_reminder"]
    reminder_id: int


class SaveProduct(Strict):
    kind: Literal["save_product"]
    product_id: int | None = Field(
        description="Id of a saved product to update ([product N]); null to add a new one."
    )
    name: str = Field(
        description="Name in Russian with brand and the key feature: 'Молоко Простоквашино 2,5%'."
    )
    brand: str | None
    kcal: float = Field(description="Per 100 g (or 100 ml).")
    protein: float = Field(description="Grams per 100 g.")
    fat: float = Field(description="Grams per 100 g.")
    carbs: float = Field(description="Grams per 100 g.")
    portion_name: str | None = Field(description="Usual portion: 'стакан', 'батончик', 'баночка'.")
    portion_grams: float | None = Field(description="Grams in that portion.")
    package_grams: float | None = Field(description="Package size in grams or ml, if known.")
    comment: str | None = Field(description="Anything worth keeping: taste, where to buy.")
    use_photos: bool = Field(
        description="Keep the photos of the current message as this product's label photos."
    )


class DeleteProduct(Strict):
    kind: Literal["delete_product"]
    product_id: int


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
    | DeleteReminder
    | SaveProduct
    | DeleteProduct,
    Field(discriminator="kind"),
]


class TurnResult(Strict):
    reply: str = Field(
        description="Message to the user in Russian, plain text, 1-4 short sentences unless "
        "they asked for detail. Do not repeat meal items or numbers: the app shows a card."
    )
    actions: list[Action]
