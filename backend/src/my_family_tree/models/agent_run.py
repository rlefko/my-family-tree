"""AgentRun aggregate. Records every LLM-driven loop (chat turn, deep-research,
conflict-resolver, dedup) with budgets, status, and final result_json."""

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
    int_column,
    jsonb_column,
    pk_column,
    text_column,
)
from my_family_tree.models.enums import AgentRole, RunStatus


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_run"

    id: UUID = pk_column()
    conversation_id: UUID | None = fk_column("conversation.id", ondelete="SET NULL", nullable=True)
    role: AgentRole = enum_column(AgentRole, "agent_role", nullable=False, index=True)

    goal: str = text_column(nullable=False)
    status: RunStatus = enum_column(
        RunStatus, "run_status", nullable=False, default=RunStatus.queued, index=True
    )
    parent_run_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    model: str = Field(max_length=120, nullable=False)
    provider: str = Field(max_length=64, nullable=False)
    budget_tokens: int = int_column(nullable=False, default=200_000)
    budget_tool_calls: int = int_column(nullable=False, default=40)
    tokens_used: int = int_column(nullable=False, default=0)
    tool_calls_used: int = int_column(nullable=False, default=0)

    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    ended_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    error: str | None = text_column()
    result_json: dict | None = jsonb_column(nullable=True, default=None)

    created_at: datetime = created_at_column()
