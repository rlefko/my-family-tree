"""Event tools: propose-create / update with participant role wiring."""

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


EventTypeStr = Literal[
    "birth",
    "death",
    "baptism",
    "burial",
    "marriage",
    "divorce",
    "immigration",
    "emigration",
    "residence",
    "census",
    "military",
    "occupation",
    "education",
    "religion",
    "will",
    "probate",
    "other",
]

ParticipantRoleStr = Literal[
    "principal",
    "spouse",
    "father",
    "mother",
    "witness",
    "officiant",
    "informant",
    "deceased",
]


class EventParticipantInput(BaseModel):
    person_id: UUID
    role: ParticipantRoleStr = "principal"


class EventProposeCreateInput(BaseModel):
    type: EventTypeStr
    date_text: str | None = Field(
        default=None,
        description="Verbatim date phrase. Parsed at apply time via DateRange.from_text.",
    )
    place_id: UUID | None = None
    place_text: str | None = Field(
        default=None,
        description=(
            "Verbatim place text if you don't have a place_id yet. The applier "
            "either matches it to an existing place or expects a separate "
            "place_propose_create proposal to land first."
        ),
    )
    description: str | None = None
    participants: list[EventParticipantInput] = Field(
        default_factory=list,
        description=(
            "Persons participating in the event with their role. At least one "
            "principal is required for birth/death."
        ),
    )
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=80, ge=0, le=100)


@registry.tool(
    name="event_propose_create",
    description=(
        "Propose a new event (birth, death, marriage, etc.) with its participants. "
        "Use `event_propose_update` to amend an existing event instead."
    ),
    input_model=EventProposeCreateInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def event_propose_create(ctx: ToolContext, payload: EventProposeCreateInput) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.create,
        target_type=SubjectType.event,
        payload={
            "type": payload.type,
            "date_text": payload.date_text,
            "place_id": str(payload.place_id) if payload.place_id else None,
            "place_text": payload.place_text,
            "description": payload.description,
            "participants": [
                {"person_id": str(p.person_id), "role": p.role} for p in payload.participants
            ],
        },
        rationale=payload.rationale,
        confidence=payload.confidence,
    )


class EventProposeUpdateInput(BaseModel):
    event_id: UUID
    date_text: str | None = None
    place_id: UUID | None = None
    place_text: str | None = None
    description: str | None = None
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=70, ge=0, le=100)


@registry.tool(
    name="event_propose_update",
    description="Propose an update to an existing event. Only set the fields you want to change.",
    input_model=EventProposeUpdateInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def event_propose_update(ctx: ToolContext, payload: EventProposeUpdateInput) -> ProposalRef:
    diff = payload.model_dump(exclude={"rationale", "confidence", "event_id"})
    diff = {k: (str(v) if k == "place_id" and v else v) for k, v in diff.items() if v is not None}
    return await make_proposal(
        ctx,
        action=ProposalAction.update,
        target_type=SubjectType.event,
        target_id=payload.event_id,
        payload=diff,
        rationale=payload.rationale,
        confidence=payload.confidence,
    )
