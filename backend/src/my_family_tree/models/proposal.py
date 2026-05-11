"""Proposal aggregate. The agent's only path for canonical writes."""

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
from my_family_tree.models.enums import ProposalAction, ProposalStatus, SubjectType


class Proposal(SQLModel, table=True):
    __tablename__ = "proposal"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")

    action: ProposalAction = enum_column(
        ProposalAction, "proposal_action", nullable=False, index=True
    )
    target_type: SubjectType | None = enum_column(
        SubjectType, "subject_type", nullable=True, default=None
    )
    target_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    payload_json: dict = jsonb_column(nullable=False, default=dict)
    rationale_md: str | None = text_column()
    confidence: int = small_int_column(nullable=False, default=50)

    agent_run_id: UUID | None = fk_column("agent_run.id", ondelete="SET NULL", nullable=True)

    status: ProposalStatus = enum_column(
        ProposalStatus,
        "proposal_status",
        nullable=False,
        default=ProposalStatus.pending,
        index=True,
    )
    approved_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    applied_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    canceled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    apply_error: str | None = text_column()
    approved_by: str | None = text_column()
    cancel_reason: str | None = text_column()

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
