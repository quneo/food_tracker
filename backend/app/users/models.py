from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Empty until a person who signed in with Bastion links their Telegram.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    # Bastion account (REGISTRATION=bastion): its id is the identity, the login is shown.
    bastion_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    # False when Bastion no longer lets this person into the project (synced hourly).
    bastion_active: Mapped[bool] = mapped_column(default=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str | None] = mapped_column(String(16))
    is_admin: Mapped[bool] = mapped_column(default=False)
    is_blocked: Mapped[bool] = mapped_column(default=False)
    invite_id: Mapped[int | None] = mapped_column(ForeignKey("invites.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime | None]

    profile: Mapped["Profile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="joined"
    )

    @property
    def display_name(self) -> str:
        name = " ".join(filter(None, [self.first_name, self.last_name])).strip()
        if name:
            return name
        if self.username:
            return self.username
        return f"@{self.telegram_username}" if self.telegram_username else "Без имени"

    @property
    def can_enter(self) -> bool:
        return not self.is_blocked and self.bastion_active


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("sex IN ('male', 'female')"),
        CheckConstraint("goal IN ('lose', 'maintain', 'gain')"),
        CheckConstraint("activity IN ('sedentary', 'light', 'moderate', 'high', 'very_high')"),
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    sex: Mapped[str | None] = mapped_column(String(8))
    birth_date: Mapped[date | None]
    height_cm: Mapped[float | None]
    activity: Mapped[str | None] = mapped_column(String(16))
    goal: Mapped[str | None] = mapped_column(String(16))
    target_weight_kg: Mapped[float | None]
    kcal_target: Mapped[int | None]
    protein_target: Mapped[int | None]
    fat_target: Mapped[int | None]
    carbs_target: Mapped[int | None]
    timezone: Mapped[str] = mapped_column(String(64))
    # Free text the person wants the assistant to know (diet, schedule, tastes).
    about: Mapped[str | None] = mapped_column(String(2000))
    # Save meals from the bot at once instead of waiting for "Save".
    auto_confirm_meals: Mapped[bool] = mapped_column(default=False)
    # A code that unblurs progress photos on the site (scrypt hash), and its guard rails.
    photo_pin_hash: Mapped[str | None] = mapped_column(String(200))
    photo_pin_failures: Mapped[int] = mapped_column(default=0, server_default="0")
    photo_pin_blocked_until: Mapped[datetime | None]
    # When the person asked to reset a forgotten code; the bot button confirms it.
    photo_pin_reset_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class Invite(Base):
    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    note: Mapped[str | None] = mapped_column(String(200))
    max_uses: Mapped[int] = mapped_column(default=1)
    uses: Mapped[int] = mapped_column(default=0)
    # The admin who made it (no foreign key: users already point at invites).
    created_by: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]

    def usable(self, now: datetime) -> bool:
        return (
            self.revoked_at is None
            and self.uses < self.max_uses
            and (self.expires_at is None or self.expires_at > now)
        )


class WebSession(Base):
    """Signed-in browser. The cookie holds a random token, the database only its hash."""

    __tablename__ = "web_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    # Progress photos are shown unblurred in this browser until then (after the code).
    photos_unlocked_until: Mapped[datetime | None]


class LoginRequest(Base):
    """A request the person confirms in the chat with the bot.

    purpose "login": the browser opens t.me/<bot>?start=login_<code>, the person confirms,
    and the browser that holds the poll secret gets the session.
    purpose "link": a person signed in (Bastion) opens t.me/<bot>?start=link_<code> to
    attach their Telegram account to user_id."""

    __tablename__ = "login_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'confirmed', 'rejected', 'used')"),
        CheckConstraint("purpose IN ('login', 'link')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(String(8), default="login", server_default="login")
    code: Mapped[str] = mapped_column(String(48), unique=True)
    poll_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    user_agent: Mapped[str | None] = mapped_column(String(300))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
