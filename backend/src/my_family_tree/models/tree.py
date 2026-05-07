"""Tree aggregate. v1 is single-user with one tree, but the column is
threaded through every domain table to make a multi-user transition trivial."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from my_family_tree.db.types import PgUUID
from my_family_tree.models._columns import (
    created_at_column,
    pk_column,
    soft_delete_column,
    text_column,
    updated_at_column,
)


class Tree(SQLModel, table=True):
    __tablename__ = "tree"

    id: UUID = pk_column()
    name: str = Field(max_length=200, nullable=False)
    description: str | None = text_column()
    root_person_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
    deleted_at: datetime | None = soft_delete_column()
