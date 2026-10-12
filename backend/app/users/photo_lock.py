"""A code that hides progress photos on the site.

Until the code is entered in a browser, the server sends only a heavily blurred copy of
each body photo, so nothing shows even if the page is opened over someone's shoulder or
the image address is copied. The code unlocks one browser session for a while."""

import hashlib
import hmac
import os
import re
from datetime import timedelta

from sqlalchemy.orm import Session

from app.chat import outbox
from app.core.exceptions import DomainError
from app.core.timeutil import utc_iso
from app.database import utcnow
from app.users.models import Profile, User, WebSession

PIN = re.compile(r"^\d{4,8}$")
UNLOCK_FOR = timedelta(minutes=15)
MAX_FAILURES = 5
BLOCK_FOR = timedelta(minutes=5)
RESET_FOR = timedelta(minutes=15)


def _scrypt(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    return f"scrypt${salt.hex()}${_scrypt(pin, salt).hex()}"


def matches(pin: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        return hmac.compare_digest(_scrypt(pin, bytes.fromhex(salt)), bytes.fromhex(digest))
    except ValueError:
        return False


def visible(profile: Profile, session: WebSession | None) -> bool:
    """Whether this browser may see progress photos as they are."""
    if not profile.photo_pin_hash:
        return True
    return bool(
        session and session.photos_unlocked_until and session.photos_unlocked_until > utcnow()
    )


def status(profile: Profile, session: WebSession | None) -> dict:
    blocked = profile.photo_pin_blocked_until
    return {
        "enabled": bool(profile.photo_pin_hash),
        "unlocked": bool(profile.photo_pin_hash) and visible(profile, session),
        "unlocked_until": utc_iso(session.photos_unlocked_until)
        if session and profile.photo_pin_hash and visible(profile, session)
        else None,
        "blocked_until": utc_iso(blocked) if blocked and blocked > utcnow() else None,
    }


def _check(profile: Profile, pin: str):
    """Counts wrong codes: after five in a row the code is not accepted for five minutes."""
    now = utcnow()
    if profile.photo_pin_blocked_until and profile.photo_pin_blocked_until > now:
        raise DomainError("Слишком много попыток. Попробуйте через несколько минут", 429)
    if matches(pin, profile.photo_pin_hash or ""):
        profile.photo_pin_failures = 0
        profile.photo_pin_blocked_until = None
        return
    profile.photo_pin_failures += 1
    left = MAX_FAILURES - profile.photo_pin_failures
    if left <= 0:
        profile.photo_pin_failures = 0
        profile.photo_pin_blocked_until = now + BLOCK_FOR
        raise DomainError("Неверный код. Ввод закрыт на 5 минут", 429)
    raise DomainError(f"Неверный код. Осталось попыток: {left}", 403)


def set_pin(profile: Profile, pin: str, current: str | None, session: WebSession | None):
    if not PIN.match(pin):
        raise DomainError("Код — от 4 до 8 цифр")
    if profile.photo_pin_hash:
        _check(profile, current or "")
    profile.photo_pin_hash = hash_pin(pin)
    profile.photo_pin_reset_at = None
    if session:
        session.photos_unlocked_until = None


def remove_pin(profile: Profile, current: str):
    if not profile.photo_pin_hash:
        return
    _check(profile, current)
    profile.photo_pin_hash = None


def unlock(profile: Profile, session: WebSession, pin: str):
    if not profile.photo_pin_hash:
        return
    _check(profile, pin)
    session.photos_unlocked_until = utcnow() + UNLOCK_FOR


def lock(session: WebSession):
    session.photos_unlocked_until = None


def request_reset(db: Session, user: User):
    """A forgotten code is reset from Telegram: whoever holds the open site alone can't."""
    if not user.profile.photo_pin_hash:
        raise DomainError("Код не задан")
    if not user.telegram_id:
        raise DomainError("Сбросить код можно через Telegram: сначала привяжите его")
    user.profile.photo_pin_reset_at = utcnow()
    outbox.push(
        db,
        user,
        "🔐 На сайте попросили сбросить код для фото прогресса. Сбросить?",
        [[{"text": "Сбросить код", "data": "pin:reset"}, {"text": "Нет", "data": "pin:keep"}]],
    )


def confirm_reset(profile: Profile) -> bool:
    asked = profile.photo_pin_reset_at
    profile.photo_pin_reset_at = None
    if not asked or utcnow() - asked > RESET_FOR:
        return False
    profile.photo_pin_hash = None
    profile.photo_pin_failures = 0
    profile.photo_pin_blocked_until = None
    return True
