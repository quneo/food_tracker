import logging
import math
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.bastion import BastionClient, BastionError, BastionUnavailable
from app.core.exceptions import DomainError
from app.core.security import new_token, token_hash
from app.core.timeutil import valid_zone
from app.database import utcnow
from app.media import service as media
from app.reminders.service import default_reminders
from app.users.models import Invite, LoginRequest, Profile, User, WebSession

log = logging.getLogger(__name__)
LOGIN_TTL = timedelta(minutes=10)
NOT_INVITED = (
    "Это закрытый дневник: войти можно по приглашению. "
    "Попросите ссылку-приглашение у администратора."
)
CLOSED = "Доступ к дневнику закрыт. Если это ошибка, напишите администратору."
BASTION_DOWN = "Bastion недоступен. Попробуйте войти чуть позже."
# Bastion error code -> (HTTP status, message for the person).
BASTION_ERRORS = {
    "invalid_credentials": (401, "Неверный логин или пароль."),
    "totp_required": (401, "Введите код из приложения."),
    "invalid_totp": (
        401,
        "Код не подошел. Дождитесь нового кода в приложении и попробуйте снова.",
    ),
    "totp_not_enrolled": (
        403,
        "Сначала привяжите телефон в Bastion: войдите туда один раз и отсканируйте QR-код.",
    ),
    "access_denied": (
        403,
        "У вашего аккаунта Bastion нет доступа к дневнику. Попросите администратора добавить "
        "вас в группу проекта.",
    ),
}


def link_first() -> str:
    """For a Telegram account nobody has linked yet (REGISTRATION=bastion)."""
    site = get_settings().app_url
    where = f"на сайте {site}" if site else "на сайте дневника"
    return (
        f"Дневник открывается через Bastion. Войдите {where}, затем в профиле нажмите "
        "«Привязать Telegram» — и сможете писать сюда."
    )


def by_telegram(db: Session, telegram_id: int) -> User | None:
    return db.scalar(select(User).where(User.telegram_id == telegram_id))


def _fill(user: User, info: dict):
    # People from Bastion keep the name Bastion gives them.
    if not user.bastion_id:
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
        if not user.can_enter:
            raise DomainError(CLOSED, 403)
        _fill(user, info)
        user.is_admin = user.is_admin or telegram_id in settings.admin_ids
        user.last_seen_at = utcnow()
        db.commit()
        return user, False
    if settings.registration == "bastion":
        raise DomainError(link_first(), 403, {"code": "link_required"})
    invite = find_invite(db, invite_code)
    admin = telegram_id in settings.admin_ids
    if settings.registration == "invite" and not invite and not admin:
        raise DomainError(NOT_INVITED, 403, {"code": "invite_required"})
    user = User(telegram_id=telegram_id, is_admin=admin)
    _fill(user, info)
    if invite:
        invite.uses += 1
        user.invite_id = invite.id
    _create(db, user)
    db.commit()
    return user, True


def _create(db: Session, user: User):
    """Adds a new person with a profile and the (switched off) default reminders."""
    settings = get_settings()
    zone = settings.default_timezone if valid_zone(settings.default_timezone) else "UTC"
    user.last_seen_at = utcnow()
    user.profile = Profile(timezone=zone)
    db.add(user)
    db.flush()
    db.add_all(default_reminders(user))


# Bastion


def bastion_client() -> BastionClient:
    settings = get_settings()
    if not settings.bastion_ready:
        raise DomainError("Вход через Bastion не настроен", 503, {"code": "bastion_off"})
    return BastionClient(
        settings.bastion_url, settings.bastion_client_id, settings.bastion_client_secret
    )


def _bastion_error(error: BastionError) -> DomainError:
    if error.code in BASTION_ERRORS:
        status, message = BASTION_ERRORS[error.code]
        extra = {"code": error.code}
        if error.code == "totp_not_enrolled" and get_settings().bastion_link:
            extra["bastion_url"] = get_settings().bastion_link
        return DomainError(message, status, extra)
    if error.code == "locked":
        retry = max(int(error.retry_after or 60), 1)
        return DomainError(
            f"Слишком много неудачных попыток. Попробуйте через {math.ceil(retry / 60)} мин.",
            429,
            {"code": "locked", "retry_after": retry},
        )
    if error.code == "invalid_client":
        log.error("Bastion rejected BASTION_CLIENT_ID/BASTION_CLIENT_SECRET")
        return DomainError(
            "Вход временно недоступен: дневник неверно подключен к Bastion. "
            "Сообщите администратору.",
            503,
            {"code": "invalid_client"},
        )
    log.error("Unexpected Bastion answer: HTTP %s, code %s", error.status, error.code)
    return DomainError(BASTION_DOWN, 503, {"code": "bastion_unavailable"})


def bastion_login(
    db: Session, username: str, password: str, totp_code: str | None, ip: str | None
) -> User:
    """Checks the person in Bastion; the first sign-in creates their account here."""
    try:
        account = bastion_client().authenticate(username, password, totp_code, end_user_ip=ip)
    except BastionError as error:
        raise _bastion_error(error) from None
    except (BastionUnavailable, KeyError, TypeError) as error:
        log.error("Bastion is unreachable or answered unexpectedly: %r", error)
        raise DomainError(BASTION_DOWN, 503, {"code": "bastion_unavailable"}) from None
    if not isinstance(account, dict) or not account.get("id") or not account.get("username"):
        raise DomainError(BASTION_DOWN, 503, {"code": "bastion_unavailable"})
    if not account.get("is_active", True):
        raise _bastion_error(BastionError(401, "invalid_credentials"))
    bastion_id = str(account["id"])
    user = db.scalar(select(User).where(User.bastion_id == bastion_id))
    if user is None:
        user = User(bastion_id=bastion_id)
        _create(db, user)
    if user.is_blocked:
        raise DomainError(CLOSED, 403)
    user.username = str(account["username"])[:64]
    user.first_name = (account.get("display_name") or account["username"])[:128]
    user.last_name = None
    user.bastion_active = True
    user.is_admin = user.is_admin or user.username.lower() in get_settings().admin_logins
    db.commit()
    return user


def sync_bastion(db: Session) -> int:
    """Closes the diary for people Bastion no longer lets into the project (and reopens
    it when it does again). Returns how many accounts changed."""
    if not get_settings().bastion_ready:
        return 0
    try:
        allowed = {str(person["id"]) for person in bastion_client().users()}
    except (BastionError, BastionUnavailable, KeyError, TypeError) as error:
        log.warning("Bastion sync skipped: %r", error)
        return 0
    changed = 0
    for user in db.scalars(select(User).where(User.bastion_id.is_not(None))):
        active = user.bastion_id in allowed
        if user.bastion_active != active:
            user.bastion_active = active
            changed += 1
            if not active:
                for session in db.scalars(select(WebSession).where(WebSession.user_id == user.id)):
                    db.delete(session)
    db.commit()
    return changed


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
    if not user or not user.can_enter:
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


def pending_login(db: Session, code: str, purpose: str = "login") -> LoginRequest | None:
    request = db.scalar(select(LoginRequest).where(LoginRequest.code == code))
    if (
        not request
        or request.purpose != purpose
        or request.status != "pending"
        or request.expires_at <= utcnow()
    ):
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
    if not user or not user.can_enter:
        return "rejected", None
    return "confirmed", user


# Linking Telegram to an account made on the site (Bastion)


def start_link(db: Session, user: User) -> LoginRequest:
    request = LoginRequest(
        purpose="link",
        code=new_token(18),
        poll_hash=token_hash(new_token()),
        user_id=user.id,
        expires_at=utcnow() + LOGIN_TTL,
    )
    db.add(request)
    db.commit()
    return request


def link_target(db: Session, code: str) -> User | None:
    request = pending_login(db, code, "link")
    return db.get(User, request.user_id) if request else None


def link_telegram(db: Session, code: str, info: dict, approve: bool) -> str:
    """The person answered in the chat; returns what to tell them."""
    request = pending_login(db, code, "link")
    if not request:
        raise DomainError(
            "Ссылка для привязки устарела. Нажмите «Привязать Telegram» на сайте еще раз."
        )
    if not approve:
        request.status = "rejected"
        db.commit()
        return "✖️ Привязка отменена."
    user = db.get(User, request.user_id)
    telegram_id = int(info["id"])
    owner = by_telegram(db, telegram_id)
    if owner and owner.id != user.id:
        raise DomainError("Этот Telegram уже привязан к другому аккаунту дневника.")
    user.telegram_id = telegram_id
    _fill(user, info)
    request.status = "used"
    db.commit()
    return "✅ Telegram привязан. Теперь можно присылать сюда еду, вес и вопросы."


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
