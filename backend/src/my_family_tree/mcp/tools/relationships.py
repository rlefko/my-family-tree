"""Relationship tools: propose-create / delete. Symmetric types
(`spouse_of`, `sibling_of`, `partner_of`) get inserted as two rows on apply."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import ProposalRef
from my_family_tree.mcp.tools.proposals import make_proposal
from my_family_tree.models.enums import ProposalAction, SubjectType

registry = get_registry()


_REL_TYPES = (
    "parent_of",
    "spouse_of",
    "sibling_of",
    "adoptive_parent_of",
    "step_parent_of",
    "guardian_of",
    "partner_of",
)
RelTypeStr = Literal[
    "parent_of",
    "spouse_of",
    "sibling_of",
    "adoptive_parent_of",
    "step_parent_of",
    "guardian_of",
    "partner_of",
]


class RelationshipProposeCreateInput(BaseModel):
    subject_id: UUID = Field(
        description=(
            "For asymmetric types (e.g. `parent_of`), the subject is the parent "
            "and `object_id` is the child. For symmetric types the order is "
            "irrelevant."
        ),
    )
    object_id: UUID
    type: RelTypeStr
    start_text: str | None = None
    end_text: str | None = None
    notes_md: str | None = None
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=80, ge=0, le=100)


@registry.tool(
    name="relationship_propose_create",
    description=(
        "Propose a new relationship between two persons. Symmetric types "
        "(spouse_of, sibling_of, partner_of) materialize as two rows on apply."
    ),
    input_model=RelationshipProposeCreateInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def relationship_propose_create(
    ctx: ToolContext, payload: RelationshipProposeCreateInput
) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.create,
        target_type=SubjectType.relationship,
        payload={
            "subject_id": str(payload.subject_id),
            "object_id": str(payload.object_id),
            "type": payload.type,
            "start_text": payload.start_text,
            "end_text": payload.end_text,
            "notes_md": payload.notes_md,
        },
        rationale=payload.rationale,
        confidence=payload.confidence,
    )


class RelationshipProposeDeleteInput(BaseModel):
    relationship_id: UUID
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=80, ge=0, le=100)


@registry.tool(
    name="relationship_propose_delete",
    description=(
        "Propose soft-delete of an existing relationship. The applier sets "
        "`deleted_at` rather than physically removing the row, preserving an "
        "audit trail."
    ),
    input_model=RelationshipProposeDeleteInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def relationship_propose_delete(
    ctx: ToolContext, payload: RelationshipProposeDeleteInput
) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.delete,
        target_type=SubjectType.relationship,
        target_id=payload.relationship_id,
        payload={"relationship_id": str(payload.relationship_id)},
        rationale=payload.rationale,
        confidence=payload.confidence,
    )
