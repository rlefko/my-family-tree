"""UUID v7 helpers. Time-ordered IDs improve B-tree locality on hot inserts."""

from __future__ import annotations

from uuid import UUID

import uuid_utils


def new_id() -> UUID:
    """Generate a new UUIDv7. Time-ordered, monotonic within a millisecond."""
    return UUID(str(uuid_utils.uuid7()))


def new_id_str() -> str:
    """String form, useful for log fields and external IDs."""
    return str(new_id())
