"""SQLModel/SQLAlchemy base. Single source of truth for `metadata`.

Naming convention is enforced so Alembic-generated constraints are stable across
machines and easy to identify in `psql`.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import SQLModel

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Replace SQLModel's default MetaData with one that carries our naming convention
# so generated DDL is consistent.
SQLModel.metadata = MetaData(naming_convention=NAMING_CONVENTION)

# Re-export so callers `from my_family_tree.db.base import metadata` work.
metadata = SQLModel.metadata


__all__ = ["NAMING_CONVENTION", "SQLModel", "metadata"]
