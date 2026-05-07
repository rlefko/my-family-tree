"""Conflict tools: list, get."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from my_family_tree.core.errors import NotFoundError
from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import ConflictSummary
from my_family_tree.models.conflict import Conflict
from my_family_tree.models.enums import ConflictStatus

registry = get_registry()


class ConflictListInput(BaseModel):
    status: ConflictStatus | None = ConflictStatus.open
    limit: int = Field(default=20, ge=1, le=100)


class ConflictListOutput(BaseModel):
    items: list[ConflictSummary]


@registry.tool(
    name="conflict_list",
    description="List conflicts (default: only open). Sorted by severity desc.",
    input_model=ConflictListInput,
    output_model=ConflictListOutput,
    capability=Capability.READ,
)
async def conflict_list(ctx: ToolContext, payload: ConflictListInput) -> ConflictListOutput:
    async with session_scope(ctx.session_factory) as session:
        stmt = select(Conflict).where(Conflict.tree_id == ctx.tree_id)
        if payload.status is not None:
            stmt = stmt.where(Conflict.status == payload.status)
        stmt = stmt.order_by(Conflict.severity.desc()).limit(payload.limit)
        rows = (await session.execute(stmt)).scalars().all()
        return ConflictListOutput(
            items=[
                ConflictSummary(
                    id=c.id,
                    kind=c.kind.value,
                    status=c.status.value,
                    severity=c.severity,
                    summary=c.summary,
                    subject_id=c.subject_id,
                    subject_type=c.subject_type.value,
                )
                for c in rows
            ]
        )


class ConflictGetInput(BaseModel):
    conflict_id: UUID


@registry.tool(
    name="conflict_get",
    description="Fetch a conflict with its full summary.",
    input_model=ConflictGetInput,
    output_model=ConflictSummary,
    capability=Capability.READ,
)
async def conflict_get(ctx: ToolContext, payload: ConflictGetInput) -> ConflictSummary:
    async with session_scope(ctx.session_factory) as session:
        c = await session.get(Conflict, payload.conflict_id)
        if c is None or c.tree_id != ctx.tree_id:
            raise NotFoundError(f"conflict {payload.conflict_id} not found")
        return ConflictSummary(
            id=c.id,
            kind=c.kind.value,
            status=c.status.value,
            severity=c.severity,
            summary=c.summary,
            subject_id=c.subject_id,
            subject_type=c.subject_type.value,
        )
