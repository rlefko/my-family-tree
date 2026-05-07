"""Tree-wide aggregate stats."""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import TreeStats
from my_family_tree.models.conflict import Conflict
from my_family_tree.models.document import Document
from my_family_tree.models.enums import ConflictStatus, PersonStatus, ProposalStatus
from my_family_tree.models.event import Event
from my_family_tree.models.person import Person
from my_family_tree.models.proposal import Proposal
from my_family_tree.models.relationship import Relationship

registry = get_registry()


class TreeStatsInput(BaseModel):
    pass


@registry.tool(
    name="tree_stats",
    description="Top-line counts for the active tree.",
    input_model=TreeStatsInput,
    output_model=TreeStats,
    capability=Capability.READ,
)
async def tree_stats(ctx: ToolContext, _payload: TreeStatsInput) -> TreeStats:
    async with session_scope(ctx.session_factory) as session:
        persons = await _count(
            session,
            select(func.count())
            .select_from(Person)
            .where(Person.tree_id == ctx.tree_id, Person.status == PersonStatus.active),
        )
        events = await _count(
            session,
            select(func.count()).select_from(Event).where(Event.tree_id == ctx.tree_id),
        )
        rels = await _count(
            session,
            select(func.count())
            .select_from(Relationship)
            .where(Relationship.tree_id == ctx.tree_id),
        )
        docs = await _count(
            session,
            select(func.count()).select_from(Document).where(Document.tree_id == ctx.tree_id),
        )
        conflicts_open = await _count(
            session,
            select(func.count())
            .select_from(Conflict)
            .where(Conflict.tree_id == ctx.tree_id, Conflict.status == ConflictStatus.open),
        )
        proposals_pending = await _count(
            session,
            select(func.count())
            .select_from(Proposal)
            .where(Proposal.tree_id == ctx.tree_id, Proposal.status == ProposalStatus.pending),
        )
        return TreeStats(
            persons=persons,
            events=events,
            relationships=rels,
            documents=docs,
            conflicts_open=conflicts_open,
            proposals_pending=proposals_pending,
        )


async def _count(session: AsyncSession, stmt: object) -> int:
    result = await session.execute(stmt)  # type: ignore[arg-type]
    return int(result.scalar_one())
