"""Reusable column types and helpers.

`PgUUID`: UUID column with UUIDv7 default generated app-side. We don't rely on
Postgres `gen_random_uuid()` so generation is deterministic across DB versions.

Vector and HalfVec are imported from `pgvector.sqlalchemy` and re-exported so
models import from one place.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import HALFVEC, Vector
from sqlalchemy import Dialect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator

from my_family_tree.core.ids import new_id


class PgUUID(TypeDecorator[UUID]):
    """UUID column with app-side UUIDv7 default."""

    impl = PG_UUID(as_uuid=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))

    def process_result_value(self, value: Any, dialect: Dialect) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))


def uuid7_default() -> UUID:
    """Default factory for primary keys."""
    return new_id()


__all__ = ["HALFVEC", "PgUUID", "Vector", "uuid7_default"]
