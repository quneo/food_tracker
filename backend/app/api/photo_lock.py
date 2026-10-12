from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentSession, CurrentUser, Db
from app.core.exceptions import DomainError
from app.users import photo_lock

router = APIRouter(prefix="/photo-lock", tags=["photo-lock"])


class PinIn(BaseModel):
    pin: str = Field(max_length=8)


class NewPinIn(BaseModel):
    pin: str = Field(max_length=8)
    current: str | None = Field(default=None, max_length=8)


def _guarded(db, action):
    """Wrong codes are counted even though the request fails."""
    try:
        action()
    except DomainError:
        db.commit()
        raise
    db.commit()


@router.get("")
def read_lock(user: CurrentUser, session: CurrentSession):
    return photo_lock.status(user.profile, session)


@router.put("")
def set_pin(data: NewPinIn, user: CurrentUser, session: CurrentSession, db: Db):
    _guarded(db, lambda: photo_lock.set_pin(user.profile, data.pin, data.current, session))
    return photo_lock.status(user.profile, session)


@router.post("/remove")
def remove_pin(data: PinIn, user: CurrentUser, session: CurrentSession, db: Db):
    _guarded(db, lambda: photo_lock.remove_pin(user.profile, data.pin))
    return photo_lock.status(user.profile, session)


@router.post("/unlock")
def unlock(data: PinIn, user: CurrentUser, session: CurrentSession, db: Db):
    _guarded(db, lambda: photo_lock.unlock(user.profile, session, data.pin))
    return photo_lock.status(user.profile, session)


@router.post("/lock")
def lock(user: CurrentUser, session: CurrentSession, db: Db):
    photo_lock.lock(session)
    db.commit()
    return photo_lock.status(user.profile, session)


@router.post("/reset")
def request_reset(user: CurrentUser, db: Db):
    """Sends a confirmation to the bot; the code is cleared when it is pressed there."""
    photo_lock.request_reset(db, user)
    db.commit()
    return {"sent": True}
