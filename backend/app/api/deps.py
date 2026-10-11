import hmac
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import DomainError
from app.database import get_db
from app.media.storage import Storage, get_storage
from app.users import service as users
from app.users.models import User

SESSION_COOKIE = "food_session"
Db = Annotated[Session, Depends(get_db)]


def storage() -> Storage:
    return get_storage()


Files = Annotated[Storage, Depends(storage)]


def require_bot(request: Request):
    secret = request.headers.get("X-Bot-Secret", "")
    if not hmac.compare_digest(secret.encode(), get_settings().bot_api_secret.encode()):
        raise DomainError("Нет доступа", 401)


def current_user(request: Request, db: Db) -> User:
    user = users.session_user(db, request.cookies.get(SESSION_COOKIE))
    if not user:
        raise DomainError("Войдите в дневник", 401)
    return user


def bot_user(request: Request, db: Db) -> User:
    """The person the bot acts for (X-Telegram-User), after the bot secret check."""
    require_bot(request)
    try:
        telegram_id = int(request.headers.get("X-Telegram-User", ""))
    except ValueError:
        raise DomainError("Нет пользователя Telegram", 400) from None
    user = users.by_telegram(db, telegram_id)
    if not user:
        raise DomainError("Сначала нажмите /start", 401, {"code": "not_registered"})
    if user.is_blocked:
        raise DomainError("Доступ к дневнику закрыт администратором", 403)
    return user


def admin_user(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_admin:
        raise DomainError("Только для администратора", 403)
    return user


CurrentUser = Annotated[User, Depends(current_user)]
BotUser = Annotated[User, Depends(bot_user)]
Admin = Annotated[User, Depends(admin_user)]
