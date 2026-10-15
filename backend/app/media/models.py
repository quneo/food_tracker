from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class Media(Base):
    """A photo in object storage: the original as uploaded plus a small WebP preview.

    kind: "chat" until the assistant decides what the photo is, then "meal", "body" or
    "product" (a label of a saved product).
    """

    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint("kind IN ('chat', 'meal', 'body', 'product')", name="ck_media_kind"),
        # Never hand out a deleted row's id again (see migration 0007).
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    object_key: Mapped[str] = mapped_column(String(200), unique=True)
    preview_key: Mapped[str] = mapped_column(String(200), unique=True)
    content_type: Mapped[str] = mapped_column(String(32))
    size: Mapped[int]
    width: Mapped[int]
    height: Mapped[int]
    meal_id: Mapped[int | None] = mapped_column(
        ForeignKey("meals.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PendingDeletion(Base):
    """Objects to remove from storage; retried until storage confirms."""

    __tablename__ = "pending_deletions"
    id: Mapped[int] = mapped_column(primary_key=True)
    # An object key, or a prefix ending with "/" (a whole account).
    key: Mapped[str] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
