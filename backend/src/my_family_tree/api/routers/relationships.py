"""Relationship endpoints. The tree visualization fetches the full edge set
plus the person nodes it connects, then runs a layout client-side. The
endpoint also returns marriage / divorce events so the heart joiner in the
tree can show date and place inline."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from my_family_tree.api.deps import SessionDep
from my_family_tree.models.enums import EventType, PersonStatus
from my_family_tree.models.event import Event, EventParticipant
from my_family_tree.models.person import Person
from my_family_tree.models.place import Place
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


class CoupleEvent(BaseModel):
    """A marriage or divorce that links two persons. The frontend matches
    this onto its couple unions to label the heart joiner with a date and
    place."""

    person_a_id: UUID
    person_b_id: UUID
    type: str
    date_text: str | None = None
    place_name: str | None = None


class TreeGraph(BaseModel):
    persons: list[PersonNode]
    relationships: list[RelationshipRow]
    couple_events: list[CoupleEvent] = []


@router.get("/relationships", response_model=TreeGraph)
async def list_relationships(session: SessionDep) -> TreeGraph:
    """Return every active person plus every undeleted relationship in one
    payload, suitable for a small-tree client-side layout. v1 doesn't paginate;
    we'll add tree-windowing once a tree gets big enough to need it."""
    person_stmt = select(Person).where(Person.status == PersonStatus.active)
    persons = list((await session.execute(person_stmt)).scalars().all())

    rel_stmt = select(Relationship).where(Relationship.deleted_at.is_(None))
    rels = list((await session.execute(rel_stmt)).scalars().all())

    couple_events = await _collect_couple_events(session)

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
        couple_events=couple_events,
    )


async def _collect_couple_events(session: SessionDep) -> list[CoupleEvent]:
    """Find marriage and divorce events with exactly two participants and
    return one CoupleEvent per pair. Used by the tree to label each heart
    joiner with a date and place."""
    stmt = (
        select(Event, Place)
        .outerjoin(Place, Place.id == Event.place_id)
        .where(
            Event.deleted_at.is_(None),
            Event.type.in_([EventType.marriage, EventType.divorce]),
        )
    )
    event_rows = (await session.execute(stmt)).all()
    if not event_rows:
        return []

    event_ids = [e.id for e, _ in event_rows]
    parts = (
        await session.execute(
            select(EventParticipant.event_id, EventParticipant.person_id).where(
                EventParticipant.event_id.in_(event_ids)
            )
        )
    ).all()
    by_event: dict[UUID, list[UUID]] = {}
    for ev_id, pid in parts:
        by_event.setdefault(ev_id, []).append(pid)

    out: list[CoupleEvent] = []
    couple_size = 2
    for event, place in event_rows:
        pids = by_event.get(event.id, [])
        if len(pids) != couple_size:
            continue
        a, b = sorted(pids, key=str)
        out.append(
            CoupleEvent(
                person_a_id=a,
                person_b_id=b,
                type=event.type.value,
                date_text=event.date_text,
                place_name=place.name if place is not None else None,
            )
        )
    return out
