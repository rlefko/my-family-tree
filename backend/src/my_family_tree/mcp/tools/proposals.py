"""Propose-write tools. The agent never commits canonical entities directly;
instead it creates a `proposal` row that the user (or an explicit auto-approve
policy) approves via the API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import ProposalRef
from my_family_tree.models.enums import ProposalAction, SubjectType
from my_family_tree.models.proposal import Proposal

registry = get_registry()


class PersonProposeCreateInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=400)
    given_names: str | None = None
    surname: str | None = None
    sex: str = "unknown"
    birth_text: str | None = None
    death_text: str | None = None
    notes_md: str | None = None
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=70, ge=0, le=100)


@registry.tool(
    name="person_propose_create",
    description=(
        "Propose creation of a new person. Returns a `proposal_id`. The user (or an "
        "explicit auto-approve policy) applies via the proposals API."
    ),
    input_model=PersonProposeCreateInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def person_propose_create(ctx: ToolContext, payload: PersonProposeCreateInput) -> ProposalRef:
    return await _make_proposal(
        ctx,
        action=ProposalAction.create,
        target_type=SubjectType.person,
        payload=payload.model_dump(exclude={"rationale", "confidence"}),
        rationale=payload.rationale,
        confidence=payload.confidence,
    )


async def _make_proposal(
    ctx: ToolContext,
    *,
    action: ProposalAction,
    target_type: SubjectType,
    payload: dict[str, Any],
    rationale: str,
    confidence: int,
) -> ProposalRef:
    async with session_scope(ctx.session_factory) as session:
        proposal = Proposal(
            tree_id=ctx.tree_id,
            action=action,
            target_type=target_type,
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
