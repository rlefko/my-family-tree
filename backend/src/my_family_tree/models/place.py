"""Place aggregate. Hierarchical (country/admin1/admin2/locality) with optional
geocoding. Trigram index on `normalized` is created in the migration."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, Float, String
from sqlmodel import Field, SQLModel

from my_family_tree.db.types import PgUUID
from my_family_tree.models._columns import (
    created_at_column,
    fk_column,
    pk_column,
    soft_delete_column,
    text_column,
    updated_at_column,
)


class Place(SQLModel, table=True):
    __tablename__ = "place"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")

    name: str = Field(max_length=300, nullable=False)
    normalized: str = Field(max_length=300, nullable=False, index=True)

    country_code: str | None = Field(
        default=None,
        sa_column=Column(String(length=2), nullable=True),
    )
    admin1: str | None = text_column()
    admin2: str | None = text_column()
    locality: str | None = text_column()

    latitude: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    longitude: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )

    gnis_id: str | None = text_column()
    geonames_id: str | None = text_column()

    parent_place_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
    deleted_at: datetime | None = soft_delete_column()
