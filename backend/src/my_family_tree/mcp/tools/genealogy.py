"""Genealogy MCP tools.

`genealogy_search` aggregates search across whichever genealogy providers
are configured (WikiTree, Wikidata, FamilySearch). Per-provider get-by-id
calls return richer detail with related persons grouped by relation kind.

All four tools share `Capability.WEB | Capability.READ` and gate on the
matching `enabled_when` predicate so the agent never sees a tool whose
provider is missing."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry

registry = get_registry()


class GenealogyHitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    provider_id: str
    name: str
    summary: str
    url: str | None
    birth: str | None
    death: str | None
    place: str | None
    score: float


class GenealogyRelativeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    provider_id: str | None
    relation: str
    name: str
    url: str | None
    birth: str | None = None
    death: str | None = None


class GenealogyProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    provider_id: str
    name: str
    summary: str
    url: str | None
    birth: str | None
    death: str | None
    birth_place: str | None
    death_place: str | None
    relatives: list[GenealogyRelativeOut]


class GenealogySearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    birth_year: int | None = Field(default=None, ge=1, le=3000)
    death_year: int | None = Field(default=None, ge=1, le=3000)
    place: str | None = Field(default=None, max_length=200)
    k: int | None = Field(default=None, ge=1, le=50)


class GenealogySearchOutput(BaseModel):
    results: list[GenealogyHitOut]


@registry.tool(
    name="genealogy_search",
    description=(
        "Search genealogy databases (WikiTree, Wikidata, FamilySearch) for a "
        "person by name, optionally filtered by birth year, death year, or "
        "place. Aggregates and ranks hits across enabled providers; tag the "
        "provider in any proposal so the audit trail is unambiguous."
    ),
    input_model=GenealogySearchInput,
    output_model=GenealogySearchOutput,
    capability=Capability.WEB | Capability.READ,
    enabled_when=lambda s: s.genealogy.any_enabled,
)
async def genealogy_search(
    ctx: ToolContext, payload: GenealogySearchInput
) -> GenealogySearchOutput:
    if ctx.genealogy is None:
        raise ExternalProviderError("genealogy service is not configured")
    hits = await ctx.genealogy.search(
        payload.query,
        k=payload.k,
        birth_year=payload.birth_year,
        death_year=payload.death_year,
        place=payload.place,
    )
    return GenealogySearchOutput(results=[GenealogyHitOut.model_validate(h) for h in hits])


class WikitreeGetPersonInput(BaseModel):
    wikitree_id: str = Field(
        min_length=1,
        max_length=200,
        description="WikiTree id, e.g. `Smith-1234` or numeric Id.",
    )


@registry.tool(
    name="wikitree_get_person",
    description=(
        "Fetch a public WikiTree profile with parents, spouses, siblings, and "
        "children. Refuses non-public or living profiles. The page itself can "
        "be added to the searchable knowledge base via `external_index_url`."
    ),
    input_model=WikitreeGetPersonInput,
    output_model=GenealogyProfileOut,
    capability=Capability.WEB | Capability.READ,
    enabled_when=lambda s: s.genealogy.wikitree_enabled,
)
async def wikitree_get_person(
    ctx: ToolContext, payload: WikitreeGetPersonInput
) -> GenealogyProfileOut:
    if ctx.genealogy is None or not ctx.genealogy.has("wikitree"):
        raise ExternalProviderError("wikitree provider is not enabled")
    profile = await ctx.genealogy.get_person("wikitree", payload.wikitree_id)
    return GenealogyProfileOut.model_validate(profile)


class FamilysearchGetPersonInput(BaseModel):
    person_id: str = Field(
        min_length=1,
        max_length=200,
        description="FamilySearch person id (PID), e.g. `KW1F-XYZ`.",
    )


@registry.tool(
    name="familysearch_get_person",
    description=(
        "Fetch a FamilySearch person record (deceased only) with linked "
        "relationships. Requires FAMILYSEARCH_CLIENT_ID and "
        "FAMILYSEARCH_CLIENT_SECRET. Refuses any profile flagged as living."
    ),
    input_model=FamilysearchGetPersonInput,
    output_model=GenealogyProfileOut,
    capability=Capability.WEB | Capability.READ,
    enabled_when=lambda s: s.genealogy.familysearch_enabled,
)
async def familysearch_get_person(
    ctx: ToolContext, payload: FamilysearchGetPersonInput
) -> GenealogyProfileOut:
    if ctx.genealogy is None or not ctx.genealogy.has("familysearch"):
        raise ExternalProviderError("familysearch provider is not enabled")
    profile = await ctx.genealogy.get_person("familysearch", payload.person_id)
    return GenealogyProfileOut.model_validate(profile)


class WikidataGetEntityInput(BaseModel):
    qid: str = Field(
        pattern=r"^Q\d+$",
        max_length=20,
        description="Wikidata QID, e.g. `Q7259` for Ada Lovelace.",
    )


@registry.tool(
    name="wikidata_get_entity",
    description=(
        "Fetch a Wikidata entity by QID, surfacing dates of birth/death, "
        "places, and parent/spouse/child relationships from standard "
        "genealogy properties (P22, P25, P26, P40, P569, P570, P19, P20)."
    ),
    input_model=WikidataGetEntityInput,
    output_model=GenealogyProfileOut,
    capability=Capability.WEB | Capability.READ,
    enabled_when=lambda s: s.genealogy.wikidata_enabled,
)
async def wikidata_get_entity(
    ctx: ToolContext, payload: WikidataGetEntityInput
) -> GenealogyProfileOut:
    if ctx.genealogy is None or not ctx.genealogy.has("wikidata"):
        raise ExternalProviderError("wikidata provider is not enabled")
    profile = await ctx.genealogy.get_person("wikidata", payload.qid)
    return GenealogyProfileOut.model_validate(profile)
