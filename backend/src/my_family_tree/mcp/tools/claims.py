"""Claim tools: propose accept / reject. Accepting a claim writes a
`fact_provenance` row that links the canonical fact back to the underlying
chunk + source."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import ProposalRef
from my_family_tree.mcp.tools.proposals import make_proposal
from my_family_tree.models.enums import ProposalAction

registry = get_registry()


class ClaimProposeAcceptInput(BaseModel):
    claim_id: UUID
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=85, ge=0, le=100)


@registry.tool(
    name="claim_propose_accept",
    description=(
        "Propose accepting a pending claim. On approval, the claim's status "
        "flips to `accepted` and a `fact_provenance` row is written. If the "
        "claim implies a canonical write that hasn't happened yet (e.g. a "
        "person_attr claim updates Person), the applier fans out."
    ),
    input_model=ClaimProposeAcceptInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def claim_propose_accept(ctx: ToolContext, payload: ClaimProposeAcceptInput) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.accept_claim,
        target_type=None,
        target_id=payload.claim_id,
        payload={"claim_id": str(payload.claim_id)},
        rationale=payload.rationale,
        confidence=payload.confidence,
    )


class ClaimProposeRejectInput(BaseModel):
    claim_id: UUID
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=80, ge=0, le=100)


@registry.tool(
    name="claim_propose_reject",
    description="Propose rejecting a pending claim. On approval, status flips to `rejected`.",
    input_model=ClaimProposeRejectInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def claim_propose_reject(ctx: ToolContext, payload: ClaimProposeRejectInput) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.reject_claim,
        target_type=None,
        target_id=payload.claim_id,
        payload={"claim_id": str(payload.claim_id)},
        rationale=payload.rationale,
        confidence=payload.confidence,
    )
