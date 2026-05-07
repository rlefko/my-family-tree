"""Claim + FactProvenance.

Claims are the only thing the LLM writes during ingestion. A claim is an
attributable assertion. Updates to canonical entities only happen via accepted
claims (driven by an approved `proposal`), which write a `fact_provenance` row
so we can answer "why do we believe X?"."""

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
    jsonb_column,
    pk_column,
    small_int_column,
    text_column,
    updated_at_column,
)
from my_family_tree.models.enums import ClaimKind, ClaimStatus, SubjectType


class Claim(SQLModel, table=True):
    __tablename__ = "claim"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")

    kind: ClaimKind = enum_column(ClaimKind, "claim_kind", nullable=False, index=True)
    status: ClaimStatus = enum_column(
        ClaimStatus, "claim_status", nullable=False, default=ClaimStatus.proposed, index=True
    )

    subject_type: SubjectType = enum_column(SubjectType, "subject_type", nullable=False, index=True)
    subject_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )
    predicate: str = Field(max_length=120, nullable=False, index=True)
    object_json: dict = jsonb_column(nullable=False, default=dict)

    source_id: UUID = fk_column("source.id", ondelete="RESTRICT")
    chunk_id: UUID | None = fk_column("chunk.id", ondelete="SET NULL", nullable=True)

    extractor: str = Field(max_length=120, nullable=False)
    confidence: int = small_int_column(nullable=False, default=50)
    rationale_md: str | None = text_column()

    accepted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    accepted_by: str | None = text_column()
    superseded_by_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()


class FactProvenance(SQLModel, table=True):
    __tablename__ = "fact_provenance"

    id: UUID = pk_column()
    subject_type: SubjectType = enum_column(SubjectType, "subject_type", nullable=False)
    subject_id: UUID = Field(
        sa_column=Column(PgUUID(), nullable=False, index=True),
    )
    predicate: str = Field(max_length=120, nullable=False, index=True)
    claim_id: UUID = fk_column("claim.id", ondelete="CASCADE")

    created_at: datetime = created_at_column()
