from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class WeighNote(Base):
    """Food weighed now and eaten later: the grams wait here until that meal is logged.

    meal_type None means "soon" (it burns after a few hours); otherwise it is for the next
    breakfast, lunch, dinner or snack and shows up when that meal's time comes.
    """

    __tablename__ = "weigh_notes"
    __table_args__ = (
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')", name="ck_weigh_notes_meal"
        ),
        CheckConstraint("status IN ('active', 'used', 'deleted')", name="ck_weigh_notes_status"),
        CheckConstraint("source IN ('web', 'bot', 'ai')", name="ck_weigh_notes_source"),
        Index("ix_weigh_notes_user_open", "user_id", "status", "expires_at"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(String(1000))
    meal_type: Mapped[str | None] = mapped_column(String(16))
    # Shown as "time to eat it" from due_from; gone after expires_at (naive UTC).
    due_from: Mapped[datetime]
    expires_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(8), default="active")
    source: Mapped[str] = mapped_column(String(8), default="web")
    meal_id: Mapped[int | None] = mapped_column(ForeignKey("meals.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    used_at: Mapped[datetime | None]
