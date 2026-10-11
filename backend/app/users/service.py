from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import DomainError
from app.core.security import new_token, token_hash
from app.core.timeutil import valid_zone
from app.database import utcnow
from app.media import service as media
from app.reminders.service import default_reminders
from app.users.models import Invite, LoginRequest, Profile, User, WebSession

LOGIN_TTL = timedelta(minutes=10)
NOT_INVITED = (
    "Это закрытый дневник: войти можно по приглашению. "
    "Попросите ссылку-приглашение у администратора."
)


def by_telegram(db: Session, telegram_id: int) -> User | None:
    return db.scalar(select(User).where(User.telegram_id == telegram_id))


def _fill(user: User, info: dict):
    user.first_name = (info.get("first_name") or "")[:128]
    user.last_name = (info.get("last_name") or "")[:128] or None
    user.telegram_username = info.get("username") or None
    user.language = info.get("language_code") or user.language


def find_invite(db: Session, code: str | None) -> Invite | None:
    if not code:
        return None
    invite = db.scalar(select(Invite).where(Invite.code == code))
    return invite if invite and invite.usable(utcnow()) else None


def ensure_user(db: Session, info: dict, invite_code: str | None = None) -> tuple[User, bool]:
    """The Telegram account's user, created on first contact. Returns (user, created).

    In invite mode a new person needs a valid invite; admins listed in the settings may
    always join (that is how the first admin gets in)."""
    settings = get_settings()
    telegram_id = int(info["id"])
    user = by_telegram(db, telegram_id)
    if user:
        if user.is_blocked:
            raise DomainError("Доступ к дневнику закрыт администратором", 403)
        _fill(user, info)
        user.is_admin = user.is_admin or telegram_id in settings.admin_ids
        user.last_seen_at = utcnow()
        db.commit()
        return user, False
    invite = find_invite(db, invite_code)
    admin = telegram_id in settings.admin_ids
    if settings.registration == "invite" and not invite and not admin:
        raise DomainError(NOT_INVITED, 403, {"code": "invite_required"})
    user = User(telegram_id=telegram_id, is_admin=admin, last_seen_at=utcnow())
    _fill(user, info)
    if invite:
        invite.uses += 1
        user.invite_id = invite.id
    zone = settings.default_timezone if valid_zone(settings.default_timezone) else "UTC"
    user.profile = Profile(timezone=zone)
    db.add(user)
    db.flush()
    db.add_all(default_reminders(user))
    db.commit()
    return user, True


# Web sessions


def create_session(db: Session, user: User, user_agent: str | None) -> str:
    token = new_token()
    now = utcnow()
    db.add(
        WebSession(
            user_id=user.id,
            token_hash=token_hash(token),
            user_agent=(user_agent or "")[:300] or None,
            expires_at=now + timedelta(days=get_settings().session_days),
        )
    )
    user.last_seen_at = now
    db.commit()
    return token


def session_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.scalar(select(WebSession).where(WebSession.token_hash == token_hash(token)))
    now = utcnow()
    if not session or session.expires_at <= now:
        return None
    user = db.get(User, session.user_id)
    if not user or user.is_blocked:
        return None
    # Touch at most every few minutes to keep writes rare.
    if now - session.last_used_at > timedelta(minutes=5):
        session.last_used_at = now
        user.last_seen_at = now
        db.commit()
    return user


def end_session(db: Session, token: str | None):
    if token:
        session = db.scalar(select(WebSession).where(WebSession.token_hash == token_hash(token)))
        if session:
            db.delete(session)
            db.commit()


def end_all_sessions(db: Session, user_id: int):
    for session in db.scalars(select(WebSession).where(WebSession.user_id == user_id)):
        db.delete(session)
    db.commit()


# Sign-in through the bot


def start_login(db: Session, user_agent: str | None) -> tuple[LoginRequest, str]:
    poll_secret = new_token()
    request = LoginRequest(
        code=new_token(18),
        poll_hash=token_hash(poll_secret),
        user_agent=(user_agent or "")[:300] or None,
        expires_at=utcnow() + LOGIN_TTL,
    )
    db.add(request)
    db.commit()
    return request, poll_secret


def pending_login(db: Session, code: str) -> LoginRequest | None:
    request = db.scalar(select(LoginRequest).where(LoginRequest.code == code))
    if not request or request.status != "pending" or request.expires_at <= utcnow():
        return None
    return request


def answer_login(db: Session, code: str, user: User, approve: bool) -> bool:
    request = pending_login(db, code)
    if not request:
        return False
    request.status = "confirmed" if approve else "rejected"
    request.user_id = user.id if approve else None
    db.commit()
    return True


def refuse_login(db: Session, code: str):
    request = pending_login(db, code)
    if request:
        request.status = "rejected"
        db.commit()


def poll_login(db: Session, code: str, poll_secret: str) -> tuple[str, User | None]:
    """-> (status, user once confirmed). A confirmed request is used up by the first poll."""
    request = db.scalar(select(LoginRequest).where(LoginRequest.code == code))
    if not request or request.poll_hash != token_hash(poll_secret):
        return "expired", None
    if request.status == "pending" and request.expires_at <= utcnow():
        return "expired", None
    if request.status != "confirmed":
        return ("expired" if request.status == "used" else request.status), None
    request.status = "used"
    db.commit()
    user = db.get(User, request.user_id)
    if not user or user.is_blocked:
        return "rejected", None
    return "confirmed", user


# Invites and accounts


def create_invite(db: Session, admin: User, note: str | None, max_uses: int, days: int | None):
    invite = Invite(
        code=new_token(9),
        note=note,
        max_uses=max_uses,
        created_by=admin.id,
        expires_at=utcnow() + timedelta(days=days) if days else None,
    )
    db.add(invite)
    db.commit()
    return invite


def invite_link(invite: Invite) -> str:
    return f"https://t.me/{get_settings().telegram_bot_username}?start=inv_{invite.code}"


def delete_account(db: Session, user: User):
    """Removes the person with everything they own; the files are queued for deletion."""
    media.drop_user_files(db, user.id)
    db.delete(user)
    db.commit()
