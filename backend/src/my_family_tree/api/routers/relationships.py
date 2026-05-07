"""Relationship endpoints. The tree visualization fetches the full edge set
plus the person nodes it connects, then runs a layout client-side."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from my_family_tree.api.deps import SessionDep
from my_family_tree.models.enums import PersonStatus
from my_family_tree.models.person import Person
from my_family_tree.models.relationship import Relationship

router = APIRouter()


class RelationshipRow(BaseModel):
    id: UUID
    subject_id: UUID
    object_id: UUID
    type: str
    confidence: int


class PersonNode(BaseModel):
    id: UUID
    display_name: str
    surname: str | None = None
    sex: str
    birth_text: str | None = None
    death_text: str | None = None
    is_living: bool


class TreeGraph(BaseModel):
    persons: list[PersonNode]
    relationships: list[RelationshipRow]


@router.get("/relationships", response_model=TreeGraph)
async def list_relationships(session: SessionDep) -> TreeGraph:
    """Return every active person plus every undeleted relationship in one
    payload, suitable for a small-tree client-side layout. v1 doesn't paginate;
    we'll add tree-windowing once a tree gets big enough to need it."""
    person_stmt = select(Person).where(Person.status == PersonStatus.active)
    persons = list((await session.execute(person_stmt)).scalars().all())

    rel_stmt = select(Relationship).where(Relationship.deleted_at.is_(None))
    rels = list((await session.execute(rel_stmt)).scalars().all())

    return TreeGraph(
        persons=[
            PersonNode(
                id=p.id,
                display_name=p.display_name,
                surname=p.surname,
                sex=p.sex.value,
                birth_text=p.birth_text,
                death_text=p.death_text,
                is_living=p.is_living,
            )
            for p in persons
        ],
        relationships=[
            RelationshipRow(
                id=r.id,
                subject_id=r.subject_id,
                object_id=r.object_id,
                type=r.type.value,
                confidence=r.confidence,
            )
            for r in rels
        ],
    )
