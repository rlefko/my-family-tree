"""Conversation aggregate. A chat thread."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from my_family_tree.models._columns import (
    created_at_column,
    fk_column,
    pk_column,
    soft_delete_column,
    text_column,
    updated_at_column,
)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversation"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")

    title: str | None = text_column()
    last_message_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    pinned: bool = Field(default=False, nullable=False)

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
    deleted_at: datetime | None = soft_delete_column()
