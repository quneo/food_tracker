from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow

# "review": instead of a message the assistant writes a review of the recent days.
REMINDER_KINDS = ("meal", "weight", "photo", "measure", "review", "custom")


class Reminder(Base):
    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('meal', 'weight', 'photo', 'measure', 'review', 'custom')",
            name="ck_reminders_kind",
        ),
        Index("ix_reminders_due", "enabled", "next_run_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    # Local wall time "HH:MM" in the person's time zone, and ISO weekdays (1 = Monday).
    time: Mapped[str] = mapped_column(String(5))
    days: Mapped[list] = mapped_column(default=lambda: [1, 2, 3, 4, 5, 6, 7])
    # Every 1-4 weeks on those days; `anchor_on` is the Monday of a week that counts.
    every_weeks: Mapped[int] = mapped_column(default=1, server_default="1")
    anchor_on: Mapped[date | None]
    text: Mapped[str | None] = mapped_column(String(300))
    enabled: Mapped[bool] = mapped_column(default=True)
    # Skip the reminder when it is already done (a meal logged in the last hours, a
    # weight today, a progress photo this week).
    smart_skip: Mapped[bool] = mapped_column(default=True)
    next_run_at: Mapped[datetime | None]
    last_sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
