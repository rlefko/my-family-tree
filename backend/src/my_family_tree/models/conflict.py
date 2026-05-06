"""Conflict + ConflictClaim.

Conflicts get a stable `id` derived from a hash of (kind, sorted subject IDs,
predicate) so re-running rule detection updates the existing row instead of
creating duplicates. The hash logic lives in `resolve/conflicts.py`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from my_family_tree.db.types import PgUUID
from my_family_tree.models._columns import (
    created_at_column,
    enum_column,
    fk_column,
    pk_column,
    small_int_column,
    text_column,
    updated_at_column,
)
from my_family_tree.models.enums import (
    ConflictKind,
    ConflictPosition,
    ConflictStatus,
    SubjectType,
)


class Conflict(SQLModel, table=True):
    __tablename__ = "conflict"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")
    kind: ConflictKind = enum_column(ConflictKind, "conflict_kind", nullable=False, index=True)
    status: ConflictStatus = enum_column(
        ConflictStatus,
        "conflict_status",
        nullable=False,
        default=ConflictStatus.open,
        index=True,
    )

    subject_type: SubjectType = enum_column(SubjectType, "subject_type", nullable=False)
    subject_id: UUID = Field(
        sa_column=Column(PgUUID(), nullable=False, index=True),
    )

    summary: str = text_column(nullable=False)
    severity: int = small_int_column(nullable=False, default=50)
    detected_by: str = Field(max_length=120, nullable=False)

    resolution_md: str | None = text_column()
    resolved_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    resolved_by: str | None = text_column()

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()


class ConflictClaim(SQLModel, table=True):
    __tablename__ = "conflict_claim"

    conflict_id: UUID = Field(
        sa_column=Column(PgUUID(), primary_key=True),
    )
    claim_id: UUID = Field(
        sa_column=Column(PgUUID(), primary_key=True),
    )
    position: ConflictPosition = enum_column(ConflictPosition, "conflict_position", nullable=False)
