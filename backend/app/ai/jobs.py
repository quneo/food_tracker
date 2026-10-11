"""Background processing of assistant requests.

A message becomes an AiJob (queued). The worker runs a few jobs at once (AI_MAX_PARALLEL),
one per person at a time so a conversation keeps its order, each with a time limit.
Database work runs in threads; the database is never held open while Codex thinks.
The answer goes to the outbox, which the bot delivers."""

import asyncio
import html
import logging
import re
from datetime import timedelta

from pydantic import ValidationError
from sqlalchemy import select

from app.ai import context, prompts, runner
from app.ai.actions import Executor
from app.ai.models import AiJob
from app.ai.schemas import TurnResult
from app.ai.strict_schema import strict_schema
from app.chat import outbox
from app.chat.models import ChatMessage, ChatState, PendingAction
from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.media import images
from app.media.models import Media
from app.media.storage import StorageError, get_storage
from app.users.models import User

log = logging.getLogger(__name__)
SCHEMA = strict_schema(TurnResult)
MAX_ATTEMPTS = 2
MAX_IMAGES = 6
ERRORS = {
    "off": "AI пока не подключен. Вес можно записать сообщением «вес 82.4», "
    "а приемы пищи — на сайте.",
    "timeout": "AI думал слишком долго и не успел ответить. Попробуйте еще раз.",
    "busy": "AI сейчас занят другими запросами. Попробуйте через минуту.",
    "bad_output": "AI ответил что-то непонятное. Попробуйте переформулировать.",
}
DEFAULT_ERROR = "Не получилось связаться с AI. Попробуйте позже — сообщение сохранено."
BOLD = re.compile(r"\*\*(.+?)\*\*")


def reply_html(text: str) -> str:
    """Plain model text -> safe Telegram HTML (only **bold** survives)."""
    return BOLD.sub(r"<b>\1</b>", html.escape(text.strip()))


class Worker:
    def __init__(self, sessions=SessionLocal, storage=None, run=None):
        self.sessions = sessions
        self.storage = storage
        self.run_runner = run or runner.run
        self.tasks: set[asyncio.Task] = set()
        self.wakeup = asyncio.Event()
        self.loop: asyncio.AbstractEventLoop | None = None

    def wake(self):
        """Safe to call from request threads."""
        if self.loop:
            self.loop.call_soon_threadsafe(self.wakeup.set)

    async def serve(self):
        self.loop = asyncio.get_running_loop()
        await asyncio.to_thread(self.recover)
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("worker tick failed")
            try:
                await asyncio.wait_for(self.wakeup.wait(), timeout=3)
            except TimeoutError:
                pass
            self.wakeup.clear()

    async def tick(self):
        free = get_settings().ai_max_parallel - len(self.tasks)
        if free <= 0:
            return
        for job_id in await asyncio.to_thread(self.claim, free):
            task = asyncio.create_task(self.process(job_id))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def drain(self):
        """Runs queued jobs until none are left (tests)."""
        while True:
            await self.tick()
            if not self.tasks:
                return
            await asyncio.gather(*list(self.tasks))

    # Steps in threads

    def recover(self):
        """Jobs cut off by a restart go back to the queue."""
        with self.sessions() as db:
            for job in db.scalars(select(AiJob).where(AiJob.status == "running")):
                job.status = "queued"
            db.commit()

    def claim(self, limit: int) -> list[int]:
        with self.sessions() as db:
            busy = set(db.scalars(select(AiJob.user_id).where(AiJob.status == "running")))
            claimed = []
            for job in db.scalars(select(AiJob).where(AiJob.status == "queued").order_by(AiJob.id)):
                if len(claimed) >= limit:
                    break
                if job.user_id in busy:
                    continue
                busy.add(job.user_id)
                job.status = "running"
                job.started_at = utcnow()
                job.attempts += 1
                claimed.append(job.id)
            db.commit()
            return claimed

    def prepare(self, job_id: int) -> tuple[str, list[bytes]]:
        storage = self.storage or get_storage()
        with self.sessions() as db:
            job = db.get(AiJob, job_id)
            user = db.get(User, job.user_id)
            message = db.get(ChatMessage, job.message_id)
            photos = db.scalars(
                select(Media).where(Media.message_id == message.id).order_by(Media.id)
            ).all()
            pictures = []
            for photo in photos[:MAX_IMAGES]:
                try:
                    pictures.append(images.for_ai(storage.get(photo.object_key)))
                except StorageError:
                    log.warning("photo %s unavailable for job %s", photo.id, job_id)
            review = job.kind == "review"
            prompt = prompts.assemble(
                context.build(db, user, message, job.days if review else None),
                "review" if review else "turn",
            )
            db.commit()  # memory facts' last_used_at
            return prompt, pictures

    def finish(self, job_id: int, answer: runner.RunnerResult):
        with self.sessions() as db:
            job = db.get(AiJob, job_id)
            user = db.get(User, job.user_id)
            message = db.get(ChatMessage, job.message_id)
            try:
                result = TurnResult.model_validate(answer.output)
            except ValidationError as error:
                log.warning("job %s: invalid answer: %s", job_id, error)
                db.rollback()
                self._fail(db, job, user, "bad_output", str(error)[:300], transient=True)
                return
            photos = db.scalars(select(Media).where(Media.message_id == message.id)).all()
            state = db.get(ChatState, user.id)
            focus = state.focus_meal_id if state else None
            outcome = Executor(db, user, list(photos), answer.model, focus).run(result)

            reply = reply_html(result.reply[: 3600 if job.kind == "review" else 3000])
            notes = "\n".join(html.escape(note) for note in outcome.notes)
            text = "\n\n".join(part for part in (reply, notes) if part) or "Готово."
            db.add(
                ChatMessage(
                    user_id=user.id,
                    role="assistant",
                    text="\n\n".join(
                        part for part in (result.reply, "\n".join(outcome.notes)) if part
                    ),
                )
            )
            buttons: list = []
            cards = list(outcome.cards)
            # One card and a short reply fit in one message.
            if len(cards) == 1 and len(text) + len(cards[0]["text"]) < 3500:
                card = cards.pop()
                text = f"{text}\n\n{card['text']}"
                buttons = card["buttons"]
            if outcome.created:
                # Undo keeps the message as it was, minus the undo button.
                undo = PendingAction(
                    user_id=user.id,
                    kind="undo",
                    payload={"items": outcome.created, "text": text, "buttons": buttons},
                    summary="Отменить записанное",
                    expires_at=utcnow() + timedelta(hours=24),
                )
                db.add(undo)
                db.flush()
                buttons = buttons + [[{"text": "↩️ Отменить", "data": f"u:{undo.id}"}]]
            outbox.push(db, user, text, buttons, job.status_message_id)
            for card in cards:
                outbox.push(db, user, card["text"], card["buttons"])

            if state:
                state.focus_meal_id = None
                if state.mode == "progress" and photos:
                    state.mode = None
            job.status = "done"
            job.finished_at = utcnow()
            job.model = answer.model
            job.result = result.model_dump()
            job.duration_ms = answer.duration_ms
            job.input_tokens = answer.input_tokens
            job.output_tokens = answer.output_tokens
            db.commit()

    def fail(self, job_id: int, error: runner.RunnerError):
        with self.sessions() as db:
            job = db.get(AiJob, job_id)
            user = db.get(User, job.user_id)
            self._fail(db, job, user, error.code, str(error), error.transient)

    def _fail(self, db, job: AiJob, user: User, code: str, detail: str, transient: bool):
        job.error = detail[:500]
        if transient and job.attempts < MAX_ATTEMPTS:
            log.info("job %s: %s, retrying", job.id, code)
            job.status = "queued"
        else:
            log.warning("job %s failed: %s", job.id, detail)
            job.status = "failed"
            job.finished_at = utcnow()
            outbox.push(
                db, user, f"😕 {ERRORS.get(code, DEFAULT_ERROR)}", [], job.status_message_id
            )
        db.commit()
        self.wake()

    # The job

    async def process(self, job_id: int):
        try:
            prompt, pictures = await asyncio.to_thread(self.prepare, job_id)
            answer = await self.run_runner(prompt, SCHEMA, pictures)
        except runner.RunnerError as error:
            await asyncio.to_thread(self.fail, job_id, error)
            return
        except Exception as error:
            log.exception("job %s crashed", job_id)
            await asyncio.to_thread(self.fail, job_id, runner.RunnerError("crash", str(error)))
            return
        try:
            await asyncio.to_thread(self.finish, job_id, answer)
        except Exception as error:
            log.exception("job %s: applying the answer failed", job_id)
            await asyncio.to_thread(self.fail, job_id, runner.RunnerError("apply", str(error)))


worker = Worker()
