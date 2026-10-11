from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow

MEMORY_CATEGORIES = (
    "goal",  # цели и планы
    "preference",  # что нравится, как удобнее
    "dislike",  # что не ест / не любит
    "allergy",  # аллергии и непереносимости
    "health",  # состояние здоровья, ограничения врача
    "habit",  # режим, привычки, расписание
    "food",  # любимые блюда, свои продукты и их КБЖУ
    "other",
)


class MemoryFact(Base):
    """Long-term memory: what the assistant knows about the person. Visible and editable
    on the site; the assistant gets the relevant facts with every request."""

    __tablename__ = "memory_facts"
    __table_args__ = (
        CheckConstraint(
            "category IN ('goal', 'preference', 'dislike', 'allergy', 'health', 'habit', "
            "'food', 'other')"
        ),
        CheckConstraint("source IN ('ai', 'user')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(16), default="other")
    text: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(8), default="ai")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    last_used_at: Mapped[datetime | None]


class AiJob(Base):
    """One request to the assistant, processed in the background."""

    __tablename__ = "ai_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')"),
        Index("ix_ai_jobs_status", "status", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    # "turn": answer a message; "review": a review of the last `days` days.
    kind: Mapped[str] = mapped_column(String(8), default="turn", server_default="turn")
    days: Mapped[int | None]
    attempts: Mapped[int] = mapped_column(default=0)
    # The bot's "thinking…" message that the answer replaces.
    status_message_id: Mapped[int | None] = mapped_column(BigInteger)
    model: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(String(500))
    result: Mapped[dict | None]
    duration_ms: Mapped[int | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
