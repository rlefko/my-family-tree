"""Event + EventParticipant. Events are the primary anchor for sourceable
facts (births, deaths, marriages, censuses, etc.)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from my_family_tree.db.types import PgUUID
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
from my_family_tree.models.enums import EventRole, EventType


class Event(SQLModel, table=True):
    __tablename__ = "event"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")
    type: EventType = enum_column(EventType, "event_type", nullable=False, index=True)

    date_text: str | None = text_column()
    date_min: date | None = date_column(index=True)
    date_max: date | None = date_column()
    date_precision: int = small_int_column(nullable=False, default=0)
    date_circa: bool = Field(default=False, nullable=False)

    place_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    description: str | None = text_column()
    confidence: int = small_int_column(nullable=False, default=100)

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
    deleted_at: datetime | None = soft_delete_column()


class EventParticipant(SQLModel, table=True):
    __tablename__ = "event_participant"

    event_id: UUID = Field(
        sa_column=Column(
            PgUUID(),
            primary_key=True,
        ),
    )
    person_id: UUID = Field(
        sa_column=Column(
            PgUUID(),
            primary_key=True,
            index=True,
        ),
    )
    role: EventRole = enum_column(EventRole, "event_role", nullable=False)
