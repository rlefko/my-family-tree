"""Reusable column factories. Each call returns a fresh `Column` so SQLAlchemy
doesn't complain about column reuse across declarative classes."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import (
    ENUM as PgEnum,  # noqa: N811  PgEnum is the conventional alias
    JSONB,
)
from sqlmodel import Field

from my_family_tree.db.types import PgUUID, uuid7_default


def pk_column() -> Any:
    return Field(
        default_factory=uuid7_default,
        sa_column=Column(PgUUID(), primary_key=True),
    )


def fk_column(
    target: str,
    *,
    nullable: bool = False,
    index: bool = True,
    ondelete: str | None = None,
) -> Any:
    return Field(
        default=None,
        sa_column=Column(
            PgUUID(),
            ForeignKey(target, ondelete=ondelete),
            nullable=nullable,
            index=index,
        ),
    )


def created_at_column() -> Any:
    return Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )


def updated_at_column() -> Any:
    return Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


def soft_delete_column() -> Any:
    return Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


def enum_column(
    enum_cls: type[StrEnum],
    name: str,
    *,
    nullable: bool = False,
    default: StrEnum | None = None,
    index: bool = False,
) -> Any:
    """Postgres ENUM column. `create_type=False` because the migration creates
    the type explicitly so multiple tables can share it."""
    return Field(
        default=default,
        sa_column=Column(
            PgEnum(
                enum_cls,
                name=name,
                create_type=False,
                values_callable=lambda c: [member.value for member in c],
            ),
            nullable=nullable,
            index=index,
        ),
    )


def jsonb_column(*, nullable: bool = False, default: Any = None) -> Any:
    return Field(
        default=default,
        sa_column=Column(JSONB, nullable=nullable),
    )


def text_column(*, nullable: bool = True, index: bool = False) -> Any:
    return Field(default=None, sa_column=Column(Text, nullable=nullable, index=index))


def small_int_column(*, nullable: bool = True, default: int | None = None) -> Any:
    return Field(default=default, sa_column=Column(SmallInteger, nullable=nullable))


def int_column(*, nullable: bool = True, default: int | None = None) -> Any:
    return Field(default=default, sa_column=Column(Integer, nullable=nullable))


def bigint_column(*, nullable: bool = True, default: int | None = None) -> Any:
    return Field(default=default, sa_column=Column(BigInteger, nullable=nullable))


def date_column(*, nullable: bool = True, index: bool = False) -> Any:
    return Field(default=None, sa_column=Column(Date, nullable=nullable, index=index))


__all__ = [
    "bigint_column",
    "created_at_column",
    "date_column",
    "enum_column",
    "fk_column",
    "int_column",
    "jsonb_column",
    "pk_column",
    "small_int_column",
    "soft_delete_column",
    "text_column",
    "updated_at_column",
]
