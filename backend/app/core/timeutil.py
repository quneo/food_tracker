"""Times are stored as naive UTC and shown in the person's own time zone."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from app.database import utcnow


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def valid_zone(name: str) -> bool:
    return name in available_timezones()


def to_local(value: datetime, tz: ZoneInfo) -> datetime:
    return value.replace(tzinfo=UTC).astimezone(tz)


def from_local(value: datetime, tz: ZoneInfo) -> datetime:
    """Local wall time (naive or aware) -> naive UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(UTC).replace(tzinfo=None)


def local_now(tz: ZoneInfo) -> datetime:
    return to_local(utcnow(), tz)


def local_today(tz: ZoneInfo) -> date:
    return local_now(tz).date()


def local_day(value: datetime, tz: ZoneInfo) -> date:
    return to_local(value, tz).date()


def utc_iso(value: datetime | None) -> str | None:
    """Moments not tied to the person's day (sign-ups, sessions): UTC with an offset."""
    return value.replace(tzinfo=UTC).isoformat(timespec="seconds") if value else None


def parse_local(text: str | None) -> datetime | None:
    """Accepts "2026-10-11T14:30", "2026-10-11 14:30" or a bare date (noon)."""
    if not text:
        return None
    text = text.strip().replace(" ", "T")
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text).replace(hour=12)
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None, second=0, microsecond=0)
