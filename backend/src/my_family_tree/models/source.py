"""Source aggregate. A source is the "where did we learn this?" record. May
back to a Document, a web URL, or a synthetic `user_assertion` source for
things the user types directly."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from my_family_tree.models._columns import (
    created_at_column,
    enum_column,
    fk_column,
    jsonb_column,
    pk_column,
    soft_delete_column,
    text_column,
    updated_at_column,
)
from my_family_tree.models.enums import SourceKind


class Source(SQLModel, table=True):
    __tablename__ = "source"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")
    kind: SourceKind = enum_column(SourceKind, "source_kind", nullable=False, index=True)

    title: str = Field(max_length=500, nullable=False)
    repository: str | None = text_column()
    citation: str | None = text_column()

    url: str | None = text_column()
    accessed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    document_id: UUID | None = fk_column("document.id", ondelete="SET NULL", nullable=True)

    meta_json: dict = jsonb_column(nullable=False, default=dict)

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
    deleted_at: datetime | None = soft_delete_column()
