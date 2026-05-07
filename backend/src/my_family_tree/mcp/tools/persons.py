"""Person tools: search, get, traverse, propose-create / update / merge."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from my_family_tree.core.dates import DatePrecision
from my_family_tree.core.errors import NotFoundError
from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import (
    DateRangeOut,
    PersonDetail,
    PersonSummary,
    ProposalRef,
)
from my_family_tree.mcp.tools.proposals import make_proposal
from my_family_tree.models.enums import PersonStatus, ProposalAction, RelType, SubjectType
from my_family_tree.models.person import Alias, Person
from my_family_tree.models.relationship import Relationship

registry = get_registry()


class PersonSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)
    include_merged: bool = False


class PersonSearchOutput(BaseModel):
    results: list[PersonSummary]


@registry.tool(
    name="person_search",
    description=(
        "Search persons by name. Matches on display name, surname, given names, "
        "and aliases using case-insensitive substring AND trigram similarity, so "
        "misspellings and partial names still find the right person. Returns up "
        "to `limit` matches ordered by similarity."
    ),
    input_model=PersonSearchInput,
    output_model=PersonSearchOutput,
    capability=Capability.READ,
)
async def person_search(ctx: ToolContext, payload: PersonSearchInput) -> PersonSearchOutput:
    """Hybrid name lookup: a substring match catches simple cases instantly and
    a trigram similarity match handles typos/partial spellings. Aliases are
    folded into the union so married/maiden names both resolve."""
    async with session_scope(ctx.session_factory) as session:
        query = payload.query.strip()
        like = f"%{query}%"
        # Trigram similarity threshold: 0.3 is permissive enough to surface
        # "Jon" -> "John" but tight enough to filter out unrelated rows on a
        # populated tree. Tune via Settings later.
        threshold = 0.3
        sim = func.greatest(
            func.similarity(Person.display_name, query),
            func.similarity(func.coalesce(Person.surname, ""), query),
            func.similarity(func.coalesce(Person.given_names, ""), query),
        )

        # Pull alias matches separately (the alias table joins back to person).
        alias_stmt = (
            select(Alias.person_id)
            .where(Alias.name.ilike(like))
            .union(
                select(Alias.person_id).where(func.similarity(Alias.name, query) >= threshold),
            )
        )

        stmt = select(Person, sim.label("score")).where(Person.tree_id == ctx.tree_id)
        if not payload.include_merged:
            stmt = stmt.where(Person.status == PersonStatus.active)
        stmt = stmt.where(
            or_(
                Person.display_name.ilike(like),
                Person.surname.ilike(like),
                Person.given_names.ilike(like),
                Person.surname_at_birth.ilike(like),
                sim >= threshold,
                Person.id.in_(alias_stmt),
            )
        )
        stmt = stmt.order_by(sim.desc()).limit(payload.limit)

        rows = list((await session.execute(stmt)).all())
        return PersonSearchOutput(results=[_to_summary(p) for p, _ in rows])


class PersonGetInput(BaseModel):
    person_id: UUID


@registry.tool(
    name="person_get",
    description="Fetch a person by id. Returns aliases and basic details.",
    input_model=PersonGetInput,
    output_model=PersonDetail,
    capability=Capability.READ,
)
async def person_get(ctx: ToolContext, payload: PersonGetInput) -> PersonDetail:
    async with session_scope(ctx.session_factory) as session:
        person = await session.get(Person, payload.person_id)
        if person is None or person.tree_id != ctx.tree_id:
            raise NotFoundError(f"person {payload.person_id} not found")
        # Follow merge redirects so callers always get the canonical row.
        while person.status == PersonStatus.merged and person.merged_into_id is not None:
            target = await session.get(Person, person.merged_into_id)
            if target is None:
                break
            person = target
        aliases_stmt = select(Alias.name).where(Alias.person_id == person.id)
        aliases = list((await session.execute(aliases_stmt)).scalars().all())
        return PersonDetail(
            **_to_summary(person).model_dump(),
            given_names=person.given_names,
            surname=person.surname,
            surname_at_birth=person.surname_at_birth,
            notes_md=person.notes_md,
            aliases=aliases,
        )


class TraversalInput(BaseModel):
    person_id: UUID
    direction: Literal["ancestors", "descendants", "both"] = "ancestors"
    max_generations: int = Field(default=4, ge=1, le=10)


class TraversalNode(BaseModel):
    person: PersonSummary
    generation: int
    relation_to_root: str


class TraversalOutput(BaseModel):
    root_id: UUID
    nodes: list[TraversalNode]


@registry.tool(
    name="person_traverse",
    description=(
        "Walk the tree from a root person. Direction is ancestors, descendants, or both. "
        "Bounded by `max_generations`."
    ),
    input_model=TraversalInput,
    output_model=TraversalOutput,
    capability=Capability.READ,
)
async def person_traverse(ctx: ToolContext, payload: TraversalInput) -> TraversalOutput:
    async with session_scope(ctx.session_factory) as session:
        root = await session.get(Person, payload.person_id)
        if root is None or root.tree_id != ctx.tree_id:
            raise NotFoundError(f"person {payload.person_id} not found")

        nodes: list[TraversalNode] = []
        seen: set[UUID] = {root.id}
        frontier: list[tuple[Person, int, str]] = [(root, 0, "self")]

        while frontier:
            current, gen, label = frontier.pop(0)
            nodes.append(
                TraversalNode(
                    person=_to_summary(current),
                    generation=gen,
                    relation_to_root=label,
                )
            )
            if gen >= payload.max_generations:
                continue
            edges_stmt = select(Relationship).where(
                Relationship.tree_id == ctx.tree_id,
                Relationship.type == RelType.parent_of,
            )
            if payload.direction in ("ancestors", "both"):
                # Parents of `current` are subjects of parent_of edges where object=current.
                up_stmt = edges_stmt.where(Relationship.object_id == current.id)
                for edge in (await session.execute(up_stmt)).scalars().all():
                    parent = await session.get(Person, edge.subject_id)
                    if parent is not None and parent.id not in seen:
                        seen.add(parent.id)
                        frontier.append((parent, gen + 1, _label_for("parent", gen + 1)))
            if payload.direction in ("descendants", "both"):
                down_stmt = edges_stmt.where(Relationship.subject_id == current.id)
                for edge in (await session.execute(down_stmt)).scalars().all():
                    child = await session.get(Person, edge.object_id)
                    if child is not None and child.id not in seen:
                        seen.add(child.id)
                        frontier.append((child, gen + 1, _label_for("child", gen + 1)))

        return TraversalOutput(root_id=root.id, nodes=nodes)


def _to_summary(p: Person) -> PersonSummary:
    return PersonSummary(
        id=p.id,
        display_name=p.display_name,
        sex=p.sex.value,
        birth=DateRangeOut(
            text=p.birth_text,
            min=p.birth_min,
            max=p.birth_max,
            precision=p.birth_precision or DatePrecision.UNKNOWN.value,
            circa=p.birth_circa,
        ),
        death=DateRangeOut(
            text=p.death_text,
            min=p.death_min,
            max=p.death_max,
            precision=p.death_precision or DatePrecision.UNKNOWN.value,
            circa=p.death_circa,
        ),
        confidence=p.confidence,
    )


_GRAND = 2  # generations between root and grandparent / grandchild


def _label_for(kind: Literal["parent", "child"], gen: int) -> str:
    if gen == 1:
        return kind
    if gen == _GRAND:
        return f"grand{kind}"
    return f"{'great-' * (gen - _GRAND)}grand{kind}"


# --- propose-write tools ----------------------------------------------------


class PersonProposeCreateInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=400)
    given_names: str | None = None
    surname: str | None = None
    surname_at_birth: str | None = None
    suffix: str | None = None
    sex: Literal["male", "female", "unknown"] = "unknown"
    birth_text: str | None = Field(
        default=None,
        description="Verbatim birth-date phrase, e.g. 'April 15, 1932' or 'circa 1842'.",
    )
    birth_place_text: str | None = Field(
        default=None,
        description=(
            "Verbatim birth place, e.g. 'Boston, MA'. The applier looks up or queues a place row."
        ),
    )
    death_text: str | None = None
    death_place_text: str | None = None
    is_living: bool = True
    aliases: list[str] = Field(default_factory=list)
    notes_md: str | None = None
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=70, ge=0, le=100)


@registry.tool(
    name="person_propose_create",
    description=(
        "Propose creation of a new person. Returns a `proposal_id`. Always call "
        "`person_search` first to avoid duplicating an existing person."
    ),
    input_model=PersonProposeCreateInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def person_propose_create(ctx: ToolContext, payload: PersonProposeCreateInput) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.create,
        target_type=SubjectType.person,
        payload=payload.model_dump(exclude={"rationale", "confidence"}),
        rationale=payload.rationale,
        confidence=payload.confidence,
    )


class PersonProposeUpdateInput(BaseModel):
    person_id: UUID
    display_name: str | None = Field(default=None, max_length=400)
    given_names: str | None = None
    surname: str | None = None
    surname_at_birth: str | None = None
    suffix: str | None = None
    sex: Literal["male", "female", "unknown"] | None = None
    birth_text: str | None = None
    birth_place_text: str | None = None
    death_text: str | None = None
    death_place_text: str | None = None
    is_living: bool | None = None
    notes_md: str | None = None
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=70, ge=0, le=100)


@registry.tool(
    name="person_propose_update",
    description=(
        "Propose an update to an existing person. Only fields you set are applied; "
        "omitted fields are left unchanged. Use this to add a missing birth date, "
        "fix a misspelling, etc."
    ),
    input_model=PersonProposeUpdateInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def person_propose_update(ctx: ToolContext, payload: PersonProposeUpdateInput) -> ProposalRef:
    payload_dict = payload.model_dump(exclude={"rationale", "confidence", "person_id"})
    payload_dict = {k: v for k, v in payload_dict.items() if v is not None}
    return await make_proposal(
        ctx,
        action=ProposalAction.update,
        target_type=SubjectType.person,
        target_id=payload.person_id,
        payload=payload_dict,
        rationale=payload.rationale,
        confidence=payload.confidence,
    )


class PersonProposeMergeInput(BaseModel):
    winner_id: UUID = Field(description="The person to keep.")
    loser_id: UUID = Field(description="The person to merge into the winner.")
    rationale: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(default=80, ge=0, le=100)


@registry.tool(
    name="person_propose_merge",
    description=(
        "Propose merging two persons into one. On approval, the loser's relationships, "
        "events, aliases, and claims are rewritten to point at the winner; the loser "
        "stays as `status=merged` so historical IDs still resolve."
    ),
    input_model=PersonProposeMergeInput,
    output_model=ProposalRef,
    capability=Capability.PROPOSE,
    is_read_only=False,
)
async def person_propose_merge(ctx: ToolContext, payload: PersonProposeMergeInput) -> ProposalRef:
    return await make_proposal(
        ctx,
        action=ProposalAction.merge,
        target_type=SubjectType.person,
        target_id=payload.winner_id,
        payload={
            "winner_id": str(payload.winner_id),
            "loser_id": str(payload.loser_id),
        },
        rationale=payload.rationale,
        confidence=payload.confidence,
    )
