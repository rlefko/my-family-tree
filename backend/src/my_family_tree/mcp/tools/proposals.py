"""Shared `_make_proposal` helper for every propose-* tool. The actual
domain-specific propose tools live next to their search/get cousins:
`tools/persons.py`, `tools/relationships.py`, etc. Centralizing the helper
here keeps the proposal-row writing logic in one place."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.schemas import ProposalRef
from my_family_tree.models.enums import ProposalAction, SubjectType
from my_family_tree.models.proposal import Proposal


async def make_proposal(
    ctx: ToolContext,
    *,
    action: ProposalAction,
    target_type: SubjectType | None,
    payload: dict[str, Any],
    rationale: str,
    confidence: int,
    target_id: UUID | None = None,
) -> ProposalRef:
    """Persist a proposal row and return a `ProposalRef`. The proposal is
    `pending` until the user approves it via `POST /proposals/{id}/approve`."""
    async with session_scope(ctx.session_factory) as session:
        proposal = Proposal(
            tree_id=ctx.tree_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload_json=payload,
            rationale_md=rationale,
            confidence=confidence,
        )
        session.add(proposal)
        await session.flush()
        return ProposalRef(
            proposal_id=proposal.id,
            rationale=rationale,
            confidence=confidence,
        )
