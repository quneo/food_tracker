from fastapi import APIRouter, BackgroundTasks, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import SESSION_COOKIE, CurrentUser, Db, Files, purge_later
from app.config import get_settings
from app.core import telegram_auth
from app.core.exceptions import DomainError
from app.core.timeutil import utc_iso
from app.users import service as users
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class WidgetLogin(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str
    invite: str | None = Field(default=None, max_length=64)


class WebAppLogin(BaseModel):
    init_data: str = Field(max_length=8192)
    invite: str | None = Field(default=None, max_length=64)


class LoginPoll(BaseModel):
    code: str = Field(max_length=64)
    poll_token: str = Field(max_length=128)


class DeleteAccount(BaseModel):
    confirm: str


def me(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.display_name,
        "first_name": user.first_name,
        "username": user.telegram_username,
        "telegram_id": user.telegram_id,
        "is_admin": user.is_admin,
        "timezone": user.profile.timezone,
        "created_at": utc_iso(user.created_at),
    }


def sign_in(db, user: User, request: Request, response: Response, embedded: bool = False):
    token = users.create_session(db, user, request.headers.get("user-agent"))
    settings = get_settings()
    # Inside Telegram's web client the app runs in a frame: such cookies must be
    # SameSite=None (and therefore Secure) to reach us.
    cross_site = embedded and settings.cookie_secure
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="none" if cross_site else "lax",
        partitioned=cross_site,
        path="/",
    )
    return me(user)


@router.get("/config")
def config():
    settings = get_settings()
    return {
        "bot_username": settings.telegram_bot_username,
        "registration": settings.registration,
        # The Login Widget only works on the domain set in BotFather (/setdomain).
        "widget": bool(settings.app_url and settings.app_url.startswith("https://")),
    }


@router.post("/telegram")
def widget_login(data: WidgetLogin, request: Request, response: Response, db: Db):
    fields = data.model_dump(exclude={"invite"}, exclude_none=True)
    try:
        info = telegram_auth.check_widget(fields, get_settings().telegram_bot_token)
    except telegram_auth.InvalidSignature:
        raise DomainError("Telegram не подтвердил вход. Попробуйте еще раз", 401) from None
    user, _ = users.ensure_user(db, info, data.invite)
    return sign_in(db, user, request, response)


@router.post("/webapp")
def webapp_login(data: WebAppLogin, request: Request, response: Response, db: Db):
    try:
        info = telegram_auth.check_webapp(data.init_data, get_settings().telegram_bot_token)
    except telegram_auth.InvalidSignature:
        raise DomainError("Telegram не подтвердил вход. Откройте приложение заново", 401) from None
    user, _ = users.ensure_user(db, info, data.invite)
    return sign_in(db, user, request, response, embedded=True)


@router.post("/login-requests")
def start_bot_login(request: Request, db: Db):
    login, poll_token = users.start_login(db, request.headers.get("user-agent"))
    username = get_settings().telegram_bot_username
    return {
        "code": login.code,
        "poll_token": poll_token,
        "link": f"https://t.me/{username}?start=login_{login.code}",
        "expires_in": int(users.LOGIN_TTL.total_seconds()),
    }


@router.post("/login-requests/poll")
def poll_bot_login(data: LoginPoll, request: Request, response: Response, db: Db):
    status, user = users.poll_login(db, data.code, data.poll_token)
    result: dict[str, object] = {"status": status}
    if user:
        result["user"] = sign_in(db, user, request, response)
    return result


@router.get("/me")
def whoami(user: CurrentUser):
    return me(user)


@router.post("/logout", status_code=204)
def logout(request: Request, db: Db):
    users.end_session(db, request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.post("/logout-all", status_code=204)
def logout_everywhere(user: CurrentUser, db: Db):
    users.end_all_sessions(db, user.id)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.delete("/account", status_code=204)
def delete_account(
    data: DeleteAccount, user: CurrentUser, db: Db, files: Files, background: BackgroundTasks
):
    if data.confirm.strip().lower() != "удалить":
        raise DomainError("Чтобы удалить аккаунт, напишите слово «удалить»")
    users.delete_account(db, user)
    purge_later(background, db, files)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
