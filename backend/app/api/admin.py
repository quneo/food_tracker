"""Administration: invites and accounts. Admins see who uses the app and how much, never
anyone's meals, photos, conversations or memory."""

from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.ai.models import AiJob
from app.api.deps import Admin, Db, Files, purge_later
from app.config import get_settings
from app.core.exceptions import DomainError, NotFound
from app.core.timeutil import utc_iso
from app.database import utcnow
from app.nutrition.models import Meal
from app.users import service as users
from app.users.models import Invite, User

router = APIRouter(prefix="/admin", tags=["admin"])


class InviteIn(BaseModel):
    note: str | None = Field(default=None, max_length=200)
    max_uses: int = Field(default=1, ge=1, le=100)
    days: int | None = Field(default=14, ge=1, le=365)


class UserPatch(BaseModel):
    is_blocked: bool


def invite_out(invite: Invite) -> dict:
    return {
        "id": invite.id,
        "note": invite.note,
        "link": users.invite_link(invite),
        "max_uses": invite.max_uses,
        "uses": invite.uses,
        "created_at": utc_iso(invite.created_at),
        "expires_at": utc_iso(invite.expires_at),
        "revoked": invite.revoked_at is not None,
        "usable": invite.usable(utcnow()),
    }


@router.get("/users")
def list_users(admin: Admin, db: Db):
    meals = dict(db.execute(select(Meal.user_id, func.count(Meal.id)).group_by(Meal.user_id)).all())
    rows = db.scalars(select(User).order_by(User.created_at)).all()
    return [
        {
            "id": user.id,
            "name": user.display_name,
            "username": user.telegram_username,
            "login": user.username,
            "telegram": user.telegram_id is not None,
            "bastion_active": user.bastion_active,
            "is_admin": user.is_admin,
            "is_blocked": user.is_blocked,
            "created_at": utc_iso(user.created_at),
            "last_seen_at": utc_iso(user.last_seen_at),
            "meals": meals.get(user.id, 0),
        }
        for user in rows
    ]


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserPatch, admin: Admin, db: Db):
    user = db.get(User, user_id)
    if not user:
        raise NotFound("Пользователь не найден")
    if user.id == admin.id:
        raise DomainError("Нельзя заблокировать самого себя")
    user.is_blocked = data.is_blocked
    if data.is_blocked:
        users.end_all_sessions(db, user.id)
    db.commit()
    return {"id": user.id, "is_blocked": user.is_blocked}


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: Admin, db: Db, files: Files, background: BackgroundTasks):
    user = db.get(User, user_id)
    if not user:
        raise NotFound("Пользователь не найден")
    if user.id == admin.id:
        raise DomainError("Свой аккаунт удаляется в профиле")
    users.delete_account(db, user)
    purge_later(background, db, files)
    return Response(status_code=204)


@router.get("/invites")
def list_invites(admin: Admin, db: Db):
    rows = db.scalars(select(Invite).order_by(Invite.created_at.desc())).all()
    return [invite_out(invite) for invite in rows]


@router.post("/invites", status_code=201)
def create_invite(data: InviteIn, admin: Admin, db: Db):
    return invite_out(users.create_invite(db, admin, data.note, data.max_uses, data.days))


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, admin: Admin, db: Db):
    invite = db.get(Invite, invite_id)
    if not invite:
        raise NotFound("Приглашение не найдено")
    invite.revoked_at = invite.revoked_at or utcnow()
    db.commit()
    return Response(status_code=204)


@router.get("/ai")
def ai_status(admin: Admin, db: Db):
    """Health of the assistant over the last day: counts and timings only."""
    since = utcnow() - timedelta(days=1)
    jobs = db.scalars(select(AiJob).where(AiJob.created_at >= since)).all()
    done = [job.duration_ms for job in jobs if job.status == "done" and job.duration_ms]
    last_error = next(
        (job.error for job in sorted(jobs, key=lambda job: job.id, reverse=True) if job.error),
        None,
    )
    return {
        "runner": get_settings().ai_runner,
        "queued": sum(job.status in ("queued", "running") for job in jobs),
        "done": len(done),
        "failed": sum(job.status == "failed" for job in jobs),
        "average_ms": int(sum(done) / len(done)) if done else None,
        "last_error": last_error.split(":")[0] if last_error else None,
    }
