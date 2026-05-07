"""Place tools: search and propose-create. The applier uses a trigram match
on `normalized` to dedupe before INSERT."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import PlaceSummary, ProposalRef
from my_family_tree.mcp.tools.proposals import make_proposal
from my_family_tree.models.enums import ProposalAction, SubjectType
from my_family_tree.models.place import Place

registry = get_registry()


class PlaceSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


class PlaceSearchOutput(BaseModel):
    results: list[PlaceSummary]


@registry.tool(
    name="place_search",
    description=(
        "Search places by normalized name. Call before `place_propose_create` "
        "to avoid duplicating an existing place."
    ),
    input_model=PlaceSearchInput,
    output_model=PlaceSearchOutput,
    capability=Capability.READ,
)
async def place_search(ctx: ToolContext, payload: PlaceSearchInput) -> PlaceSearchOutput:
    async with session_scope(ctx.session_factory) as session:
        like = f"%{payload.query.lower()}%"
        stmt = (
            select(Place)
            .where(Place.tree_id == ctx.tree_id)
            .where(Place.normalized.ilike(like))
            .limit(payload.limit)
        )
        rows = (await session.execute(stmt)).scalars().all()
        return PlaceSearchOutput(
            results=[
                PlaceSummary(
                    id=p.id,
                    name=p.name,
                    normalized=p.normalized,
                    country_code=p.country_code,
                    admin1=p.admin1,
                    admin2=p.admin2,
                )
                for p in rows
            ]
        )


class PlaceProposeCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    country_code: str | None = Field(default=None, max_length=2)
    admin1: str | None = None
    admin2: str | None = None
    locality: str | None = None
    parent_place_id: UUID | None = None
    latitude: float | None = None
    longitude: float | None = None
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=80, ge=0, le=100)


@registry.tool(
    name="place_propose_create",
    description=(
        "Propose creation of a new place. The applier dedupes on a trigram "
        "match against existing places' `normalized` column; if a strong match "
        "exists the apply errors and surfaces the candidate id."
    ),
    input_model=PlaceProposeCreateInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def place_propose_create(ctx: ToolContext, payload: PlaceProposeCreateInput) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.create,
        target_type=SubjectType.place,
        payload=payload.model_dump(exclude={"rationale", "confidence"}),
        rationale=payload.rationale,
        confidence=payload.confidence,
    )
