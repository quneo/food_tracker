from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.api.deps import CurrentUser, Db
from app.core.exceptions import DomainError
from app.core.timeutil import to_local, zone
from app.reminders import service
from app.reminders.models import Reminder

router = APIRouter(prefix="/reminders", tags=["reminders"])


class ReminderIn(BaseModel):
    kind: Literal["meal", "weight", "photo", "custom"]
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    days: list[int] = Field(min_length=1, max_length=7)
    text: str | None = Field(default=None, max_length=300)
    enabled: bool = True
    smart_skip: bool = True

    @field_validator("days")
    @classmethod
    def weekdays(cls, days):
        if any(not 1 <= day <= 7 for day in days):
            raise ValueError("days are 1..7")
        return sorted(set(days))


def reminder_out(reminder: Reminder, tz_name: str) -> dict:
    return {
        "id": reminder.id,
        "kind": reminder.kind,
        "time": reminder.time,
        "days": reminder.days,
        "text": reminder.text,
        "enabled": reminder.enabled,
        "smart_skip": reminder.smart_skip,
        "description": service.describe(reminder),
        "next_run_at": (
            to_local(reminder.next_run_at, zone(tz_name)).isoformat(timespec="minutes")
            if reminder.next_run_at
            else None
        ),
    }


def apply(reminder: Reminder, data: ReminderIn, tz_name: str):
    service.parse_time(data.time)
    if data.kind == "custom" and not (data.text or "").strip():
        raise DomainError("Напишите текст напоминания")
    reminder.kind = data.kind
    reminder.time = data.time
    reminder.days = data.days
    reminder.text = (data.text or "").strip() or None
    reminder.enabled = data.enabled
    reminder.smart_skip = data.smart_skip
    service.reschedule(reminder, tz_name)


@router.get("")
def list_reminders(user: CurrentUser, db: Db):
    rows = db.scalars(
        select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.time, Reminder.id)
    )
    return [reminder_out(row, user.profile.timezone) for row in rows]


@router.post("", status_code=201)
def create_reminder(data: ReminderIn, user: CurrentUser, db: Db):
    count = len(db.scalars(select(Reminder.id).where(Reminder.user_id == user.id)).all())
    if count >= 20:
        raise DomainError("Не больше 20 напоминаний")
    reminder = Reminder(user_id=user.id)
    apply(reminder, data, user.profile.timezone)
    db.add(reminder)
    db.commit()
    return reminder_out(reminder, user.profile.timezone)


@router.put("/{reminder_id}")
def update_reminder(reminder_id: int, data: ReminderIn, user: CurrentUser, db: Db):
    reminder = service.owned(db, reminder_id, user.id)
    apply(reminder, data, user.profile.timezone)
    db.commit()
    return reminder_out(reminder, user.profile.timezone)


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(reminder_id: int, user: CurrentUser, db: Db):
    db.delete(service.owned(db, reminder_id, user.id))
    db.commit()
    return Response(status_code=204)
