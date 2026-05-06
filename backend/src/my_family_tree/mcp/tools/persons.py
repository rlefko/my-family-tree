"""Person tools: search, get, traverse."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from my_family_tree.core.dates import DatePrecision
from my_family_tree.core.errors import NotFoundError
from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import (
    DateRangeOut,
    PersonDetail,
    PersonSummary,
)
from my_family_tree.models.enums import PersonStatus, RelType
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
    description="Search persons by name with trigram similarity. Returns up to `limit` matches.",
    input_model=PersonSearchInput,
    output_model=PersonSearchOutput,
    capability=Capability.READ,
)
async def person_search(ctx: ToolContext, payload: PersonSearchInput) -> PersonSearchOutput:
    async with session_scope(ctx.session_factory) as session:
        stmt = select(Person).where(Person.tree_id == ctx.tree_id)
        if not payload.include_merged:
            stmt = stmt.where(Person.status == PersonStatus.active)
        # Simple ILIKE; trigram operators (% / similarity()) require a separate
        # SQLAlchemy expression and the GIN index from the migration. For v1
        # ILIKE is good enough and uses the trigram index for prefix matches.
        like = f"%{payload.query}%"
        stmt = stmt.where(
            or_(
                Person.display_name.ilike(like),
                Person.surname.ilike(like),
                Person.given_names.ilike(like),
            )
        ).limit(payload.limit)
        rows = (await session.execute(stmt)).scalars().all()
        return PersonSearchOutput(results=[_to_summary(p) for p in rows])


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
