"""Periodic work in the API process: reminders, file deletion, cleanup of stale rows."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select, update

from app.ai.models import AiJob
from app.chat.models import OutboxMessage, PendingAction
from app.database import SessionLocal, utcnow
from app.media import service as media
from app.media.models import Media
from app.media.storage import get_storage
from app.reminders import service as reminders
from app.users.models import LoginRequest, WebSession

log = logging.getLogger(__name__)
TICK = 30  # seconds
UNUSED_CHAT_PHOTOS = timedelta(days=7)


def every_tick():
    with SessionLocal() as db:
        reminders.send_due(db)
        media.purge(db, get_storage())


def hourly():
    now = utcnow()
    with SessionLocal() as db:
        db.execute(delete(LoginRequest).where(LoginRequest.expires_at < now - timedelta(days=1)))
        db.execute(delete(WebSession).where(WebSession.expires_at < now))
        db.execute(
            update(PendingAction)
            .where(PendingAction.status == "pending", PendingAction.expires_at < now)
            .values(status="cancelled")
        )
        db.execute(delete(PendingAction).where(PendingAction.created_at < now - timedelta(days=30)))
        db.execute(
            delete(OutboxMessage).where(
                OutboxMessage.status != "pending",
                OutboxMessage.created_at < now - timedelta(days=30),
            )
        )
        db.execute(
            update(AiJob).where(AiJob.finished_at < now - timedelta(days=30)).values(result=None)
        )
        # Photos sent in the chat that turned out to be neither food nor progress.
        stale = db.scalars(
            select(Media).where(Media.kind == "chat", Media.created_at < now - UNUSED_CHAT_PHOTOS)
        ).all()
        media.drop(db, list(stale))
        db.commit()


async def serve():
    ticks = 0
    while True:
        try:
            await asyncio.to_thread(every_tick)
            if ticks % (3600 // TICK) == 0:
                await asyncio.to_thread(hourly)
        except Exception:
            log.exception("maintenance failed")
        ticks += 1
        await asyncio.sleep(TICK)
