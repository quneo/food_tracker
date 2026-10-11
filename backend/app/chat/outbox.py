"""Messages the bot delivers to Telegram: assistant answers and reminders.

The bot polls the outbox and reports back, so answers survive a bot restart."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.chat.models import OutboxMessage
from app.database import utcnow

MAX_ATTEMPTS = 5


def view(text: str, buttons: list | None = None) -> dict:
    return {"text": text, "buttons": buttons or []}


def push(
    db: Session,
    user,
    text: str,
    buttons: list | None = None,
    edit_message_id: int | None = None,
) -> OutboxMessage | None:
    if not user.telegram_id:
        return None  # nothing to deliver to until Telegram is linked
    payload = view(text, buttons)
    if edit_message_id:
        payload["edit_message_id"] = edit_message_id
    message = OutboxMessage(user_id=user.id, chat_id=user.telegram_id, payload=payload)
    db.add(message)
    return message


def pending(db: Session, limit: int = 20) -> list[OutboxMessage]:
    return list(
        db.scalars(
            select(OutboxMessage)
            .where(OutboxMessage.status == "pending")
            .order_by(OutboxMessage.id)
            .limit(limit)
        )
    )


def report(
    db: Session,
    message: OutboxMessage,
    telegram_message_id: int | None,
    error: str | None,
    permanent: bool,
):
    if error:
        message.attempts += 1
        message.last_error = error[:300]
        if permanent or message.attempts >= MAX_ATTEMPTS:
            message.status = "failed"
    else:
        message.status = "sent"
        message.sent_at = utcnow()
        message.telegram_message_id = telegram_message_id
    db.commit()
