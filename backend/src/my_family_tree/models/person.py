"""Person + Alias aggregates. The Person is the primary node in the tree.
Date-uncertainty fields are inlined; `merged_into_id` redirects after a merge
proposal is approved (the loser stays around so historical IDs resolve)."""

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
from my_family_tree.models.enums import PersonStatus, Sex


class Person(SQLModel, table=True):
    __tablename__ = "person"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")

    display_name: str = Field(max_length=400, nullable=False, index=True)
    given_names: str | None = text_column()
    surname: str | None = text_column(index=True)
    surname_at_birth: str | None = text_column()
    name_particles: str | None = text_column()
    suffix: str | None = text_column()

    sex: Sex = enum_column(Sex, "sex", default=Sex.unknown, nullable=False)

    birth_text: str | None = text_column()
    birth_min: date | None = date_column(index=True)
    birth_max: date | None = date_column()
    birth_precision: int = small_int_column(nullable=False, default=0)
    birth_circa: bool = Field(default=False, nullable=False)
    birth_place_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    death_text: str | None = text_column()
    death_min: date | None = date_column()
    death_max: date | None = date_column()
    death_precision: int = small_int_column(nullable=False, default=0)
    death_circa: bool = Field(default=False, nullable=False)
    death_place_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    is_living: bool = Field(default=True, nullable=False)

    status: PersonStatus = enum_column(
        PersonStatus, "person_status", default=PersonStatus.active, nullable=False, index=True
    )
    merged_into_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    notes_md: str | None = text_column()
    confidence: int = small_int_column(nullable=False, default=100)

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
    deleted_at: datetime | None = soft_delete_column()


class Alias(SQLModel, table=True):
    __tablename__ = "alias"

    id: UUID = pk_column()
    person_id: UUID = fk_column("person.id", ondelete="CASCADE")
    name: str = Field(max_length=400, nullable=False)
    kind: str = Field(max_length=64, nullable=False)
    source_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
