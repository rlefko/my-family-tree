"""Source tools: propose-create. The chat agent rarely calls this directly,
since chat-asserted facts auto-create a `user_assertion` source via the
provenance writer in `services/provenance.py`. This tool is for explicit
sources the user names, e.g., a citation to a vital record."""

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


SourceKindStr = Literal[
    "vital_record",
    "census",
    "newspaper",
    "obituary",
    "church",
    "immigration",
    "military",
    "cemetery",
    "dna",
    "family_oral",
    "user_assertion",
    "other",
]


class SourceProposeCreateInput(BaseModel):
    kind: SourceKindStr
    title: str = Field(min_length=1, max_length=500)
    repository: str | None = None
    citation: str | None = None
    url: str | None = None
    document_id: UUID | None = None
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=80, ge=0, le=100)


@registry.tool(
    name="source_propose_create",
    description=(
        "Propose a new explicit source (vital record, census page, newspaper "
        "obituary, etc.). For chat-asserted facts you don't need to call this; "
        "the applier creates a synthetic `user_assertion` source automatically."
    ),
    input_model=SourceProposeCreateInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def source_propose_create(ctx: ToolContext, payload: SourceProposeCreateInput) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.create,
        target_type=SubjectType.document,  # closest enum; we lack a direct 'source' subject_type
        payload={
            "kind": payload.kind,
            "title": payload.title,
            "repository": payload.repository,
            "citation": payload.citation,
            "url": payload.url,
            "document_id": str(payload.document_id) if payload.document_id else None,
        },
        rationale=payload.rationale,
        confidence=payload.confidence,
    )
