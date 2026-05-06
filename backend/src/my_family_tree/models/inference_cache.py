"""InferenceCache. Memoizes deterministic LLM extractions on chunks so re-runs
are free. Key = sha256(model || prompt_version || input_hash)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, SQLModel

from my_family_tree.models._columns import (
    created_at_column,
    jsonb_column,
    pk_column,
)


class InferenceCache(SQLModel, table=True):
    __tablename__ = "inference_cache"

    id: UUID = pk_column()
    key: str = Field(
        sa_column=Column(String(length=128), nullable=False, unique=True, index=True),
    )
    value_json: dict = jsonb_column(nullable=False, default=dict)
    expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    created_at: datetime = created_at_column()
