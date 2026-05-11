"""Shared `make_proposal` helper for every propose-* tool plus the
cross-domain `proposal_cancel` MCP tool. Domain-specific propose tools live
next to their search/get cousins (`tools/persons.py`, etc.) and import the
helper from here."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from my_family_tree.core.errors import NotFoundError, ValidationError
from my_family_tree.core.time import utcnow
from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import ProposalRef
from my_family_tree.models.enums import ProposalAction, ProposalStatus, SubjectType
from my_family_tree.models.proposal import Proposal

registry = get_registry()


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
            agent_run_id=ctx.agent_run_id,
        )
        session.add(proposal)
        await session.flush()
        return ProposalRef(
            proposal_id=proposal.id,
            rationale=rationale,
            confidence=confidence,
        )


class ProposalCancelInput(BaseModel):
    proposal_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class ProposalCanceled(BaseModel):
    proposal_id: UUID
    status: str


@registry.tool(
    name="proposal_cancel",
    description=(
        "Withdraw a pending proposal that you queued by mistake. Sets "
        "status to `canceled` and records the reason for the audit trail. "
        "Only `pending` proposals can be canceled; approved, rejected, "
        "expired, or already canceled proposals raise an error. Use this "
        "instead of asking the user to reject your own proposal, and pair "
        "it with a corrected `*_propose_*` call when you know the right "
        "shape."
    ),
    input_model=ProposalCancelInput,
    output_model=ProposalCanceled,
    capability=Capability.TRIVIAL_WRITE,
    is_read_only=False,
)
async def proposal_cancel(ctx: ToolContext, payload: ProposalCancelInput) -> ProposalCanceled:
    async with session_scope(ctx.session_factory) as session:
        proposal = await session.get(Proposal, payload.proposal_id)
        if proposal is None or proposal.tree_id != ctx.tree_id:
            raise NotFoundError(f"proposal {payload.proposal_id} not found")
        if proposal.status != ProposalStatus.pending:
            raise ValidationError(
                f"proposal is {proposal.status.value}, only pending proposals can be canceled"
            )
        proposal.status = ProposalStatus.canceled
        proposal.canceled_at = utcnow()
        proposal.cancel_reason = payload.reason
    return ProposalCanceled(proposal_id=payload.proposal_id, status=ProposalStatus.canceled.value)
