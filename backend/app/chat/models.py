from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, utcnow


class ChatSession(Base):
    """A conversation with the assistant in the bot. Only messages inside a session reach
    the assistant; it sees the whole session. It ends on request or after a quiet spell."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        CheckConstraint("end_reason IN ('user', 'idle', 'new')", name="ck_chat_sessions_end"),
        Index("ix_chat_sessions_user_open", "user_id", "ended_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(default=utcnow)
    # The last user message the assistant has answered (later ones wait for it).
    answered_through_id: Mapped[int | None]
    ended_at: Mapped[datetime | None]
    end_reason: Mapped[str | None] = mapped_column(String(8))


class ChatMessage(Base):
    """The conversation with the assistant, as the bot saw it."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')"),
        Index("ix_chat_messages_user_created", "user_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text, default="")
    photos: Mapped[int] = mapped_column(default=0)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ChatState(Base):
    """Per-person conversation state that outlives the bot process."""

    __tablename__ = "chat_states"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # The meal the person pressed "Fix" on: the next message is about it.
    focus_meal_id: Mapped[int | None] = mapped_column(ForeignKey("meals.id", ondelete="SET NULL"))
    # "progress": photos until mode_until are body progress photos, not food.
    mode: Mapped[str | None] = mapped_column(String(16))
    mode_until: Mapped[datetime | None]
    # /new: earlier messages are no longer the current conversation.
    context_from: Mapped[datetime | None]
    # "weight" / "measure": the bot asked for numbers (keyboard button) until then.
    awaiting: Mapped[str | None] = mapped_column(String(16))
    awaiting_until: Mapped[datetime | None]
    # Which version of the keyboard under the input field the person has been sent.
    keyboard_version: Mapped[int] = mapped_column(default=0, server_default="0")


class PendingAction(Base):
    """A change that waits for the person's yes: edits and deletions of saved records,
    or an undo for what the assistant just recorded."""

    __tablename__ = "pending_actions"
    __table_args__ = (CheckConstraint("status IN ('pending', 'done', 'cancelled')"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict]
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]


class OutboxMessage(Base):
    """A message for the bot to deliver: assistant replies and reminders.

    payload: {"text": html, "buttons": [[{"text", "data"|"url"|"web_app"}]],
              "keyboard": [[label]]?, "edit_message_id": int?}
    """

    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'failed')"),
        Index("ix_outbox_status", "status", "id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict]
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    sent_at: Mapped[datetime | None]
