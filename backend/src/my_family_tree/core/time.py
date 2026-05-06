"""Timezone-aware time helpers. Always use UTC at storage boundaries."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as a tz-aware UTC datetime."""
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    """Coerce a datetime to UTC. Naive datetimes are assumed already UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
