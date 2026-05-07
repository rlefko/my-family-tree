"""Relationship edges. Symmetric relationship types (spouse_of, sibling_of,
partner_of) are stored as two rows in a single transaction; asymmetric types
(parent_of, etc.) are stored once."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlmodel import SQLModel

from my_family_tree.models._columns import (
    created_at_column,
    date_column,
    enum_column,
    fk_column,
    pk_column,
    small_int_column,
    soft_delete_column,
    text_column,
    updated_at_column,
)
from my_family_tree.models.enums import RelType


class Relationship(SQLModel, table=True):
    __tablename__ = "relationship"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")
    subject_id: UUID = fk_column("person.id", ondelete="CASCADE")
    object_id: UUID = fk_column("person.id", ondelete="CASCADE")

    type: RelType = enum_column(RelType, "rel_type", nullable=False, index=True)

    start_text: str | None = text_column()
    start_min: date | None = date_column()
    start_max: date | None = date_column()
    end_text: str | None = text_column()
    end_min: date | None = date_column()
    end_max: date | None = date_column()

    confidence: int = small_int_column(nullable=False, default=100)
    notes_md: str | None = text_column()

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
    deleted_at: datetime | None = soft_delete_column()
