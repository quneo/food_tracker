from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow
from app.media.models import Media

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
CONFIDENCE = ("low", "medium", "high")
# Where a weight came from: guessed from a photo or description, said by the person
# (or weighed), or read from a package label. Guessed weights are never shown as exact.
GRAMS_SOURCES = ("estimated", "stated", "label")


class Meal(Base):
    __tablename__ = "meals"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed')"),
        CheckConstraint("meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')"),
        CheckConstraint("source IN ('photo', 'text', 'manual')"),
        CheckConstraint("confidence IN ('low', 'medium', 'high')"),
        Index("ix_meals_user_day", "user_id", "eaten_on"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    meal_type: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    # When it was eaten (UTC) and that day in the person's time zone; created_at is when
    # the record was made, which can be much later.
    eaten_at: Mapped[datetime]
    eaten_on: Mapped[date]
    note: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str] = mapped_column(String(16), default="manual")
    kcal: Mapped[float] = mapped_column(default=0)
    protein: Mapped[float] = mapped_column(default=0)
    fat: Mapped[float] = mapped_column(default=0)
    carbs: Mapped[float] = mapped_column(default=0)
    # The estimate: how sure, a plausible range for the total, what was assumed.
    estimated_by: Mapped[str] = mapped_column(String(8), default="user")
    confidence: Mapped[str | None] = mapped_column(String(8))
    kcal_low: Mapped[float | None]
    kcal_high: Mapped[float | None]
    assumptions: Mapped[list] = mapped_column(default=list)
    ai_model: Mapped[str | None] = mapped_column(String(64))
    # The assistant's remark about this meal (short, longer when there is something to say).
    ai_comment: Mapped[str | None] = mapped_column(String(1500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    confirmed_at: Mapped[datetime | None]

    items: Mapped[list["MealItem"]] = relationship(
        cascade="all, delete-orphan", order_by="MealItem.position", lazy="selectin"
    )
    photos: Mapped[list[Media]] = relationship(
        primaryjoin="Meal.id == Media.meal_id", order_by=Media.id, lazy="selectin", viewonly=True
    )

    def recount(self):
        for field in ("kcal", "protein", "fat", "carbs"):
            setattr(self, field, round(sum(getattr(item, field) for item in self.items), 1))


class MealItem(Base):
    __tablename__ = "meal_items"
    __table_args__ = (
        CheckConstraint("grams_source IN ('estimated', 'stated', 'label')"),
        CheckConstraint("kcal >= 0 AND protein >= 0 AND fat >= 0 AND carbs >= 0"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meals.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    name: Mapped[str] = mapped_column(String(200))
    # A saved product the numbers were taken from (the person's own milk, bar, yogurt).
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    grams: Mapped[float | None]
    grams_source: Mapped[str] = mapped_column(String(16), default="estimated")
    kcal: Mapped[float] = mapped_column(default=0)
    protein: Mapped[float] = mapped_column(default=0)
    fat: Mapped[float] = mapped_column(default=0)
    carbs: Mapped[float] = mapped_column(default=0)
    confidence: Mapped[str | None] = mapped_column(String(8))
    note: Mapped[str | None] = mapped_column(String(300))


class Product(Base):
    """A product the person eats often, with numbers from its label: the assistant uses
    them instead of guessing. Values are per 100 g (or 100 ml)."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("kcal >= 0 AND protein >= 0 AND fat >= 0 AND carbs >= 0"),
        Index("ix_products_user_name", "user_id", "name"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(120))
    kcal: Mapped[float] = mapped_column(default=0)
    protein: Mapped[float] = mapped_column(default=0)
    fat: Mapped[float] = mapped_column(default=0)
    carbs: Mapped[float] = mapped_column(default=0)
    # A usual portion ("стакан", 250 g; "батончик", 40 g) and the package size.
    portion_name: Mapped[str | None] = mapped_column(String(60))
    portion_grams: Mapped[float | None]
    package_grams: Mapped[float | None]
    comment: Mapped[str | None] = mapped_column(String(1000))
    uses: Mapped[int] = mapped_column(default=0)
    last_used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    photos: Mapped[list[Media]] = relationship(
        primaryjoin="Product.id == Media.product_id",
        order_by=Media.id,
        lazy="selectin",
        viewonly=True,
    )


class DayMark(Base):
    """The person's own say on whether a day's food log is complete (for averages)."""

    __tablename__ = "day_marks"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(primary_key=True)
    complete: Mapped[bool]
