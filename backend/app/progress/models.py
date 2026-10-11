from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow
from app.media.models import Media

# Body measurements the app knows: key -> (name, unit).
MEASUREMENTS = {
    "waist": ("Талия", "cm"),
    "hips": ("Бедра", "cm"),
    "chest": ("Грудь", "cm"),
    "neck": ("Шея", "cm"),
    "arm": ("Бицепс", "cm"),
    "thigh": ("Бедро", "cm"),
    "calf": ("Голень", "cm"),
    "body_fat": ("Процент жира", "%"),
}
POSES = ("front", "side", "back", "other")


class WeightEntry(Base):
    __tablename__ = "weights"
    __table_args__ = (
        CheckConstraint("weight_kg > 0"),
        Index("ix_weights_user_day", "user_id", "measured_on"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    weight_kg: Mapped[float]
    measured_at: Mapped[datetime]
    measured_on: Mapped[date]
    note: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(8), default="web")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (
        CheckConstraint("value > 0"),
        Index("ix_measurements_user_day", "user_id", "measured_on"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[float]
    measured_at: Mapped[datetime]
    measured_on: Mapped[date]
    note: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(8), default="web")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def unit(self) -> str:
        return MEASUREMENTS.get(self.kind, ("", "cm"))[1]


class ProgressPhoto(Base):
    __tablename__ = "progress_photos"
    __table_args__ = (
        CheckConstraint("pose IN ('front', 'side', 'back', 'other')"),
        Index("ix_progress_photos_user_day", "user_id", "taken_on"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    media_id: Mapped[int] = mapped_column(ForeignKey("media.id", ondelete="CASCADE"), unique=True)
    taken_on: Mapped[date]
    pose: Mapped[str] = mapped_column(String(8), default="front")
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    media: Mapped[Media] = relationship(lazy="joined")
