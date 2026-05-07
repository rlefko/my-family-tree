"""People endpoints. The /people page lists everyone with rich row data; the
side drawer fetches detail + relationships + documents for a single person."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import case, distinct, func, or_, select
from sqlalchemy.orm import aliased

from my_family_tree.api.deps import SessionDep
from my_family_tree.core.errors import NotFoundError, ValidationError
from my_family_tree.core.time import utcnow
from my_family_tree.models.claim import Claim
from my_family_tree.models.document import Document
from my_family_tree.models.enums import (
    EventType,
    PersonStatus,
    ProposalAction,
    ProposalStatus,
    SubjectType,
)
from my_family_tree.models.event import Event, EventParticipant
from my_family_tree.models.person import Alias, Person
from my_family_tree.models.place import Place
from my_family_tree.models.proposal import Proposal
from my_family_tree.models.relationship import Relationship
from my_family_tree.models.source import Source
from my_family_tree.services.proposal_apply import (
    SYMMETRIC_RELS,
    apply_proposal,
    normalize_place_name,
)

router = APIRouter()


class PersonRow(BaseModel):
    id: UUID
    display_name: str
    sex: str
    surname: str | None = None
    given_names: str | None = None
    birth_text: str | None = None
    death_text: str | None = None
    is_living: bool
    status: str
    relationship_count: int = 0
    document_count: int = 0


class PeopleList(BaseModel):
    items: list[PersonRow]


class PlaceRef(BaseModel):
    id: UUID
    name: str
    country_code: str | None = None


class PersonDetail(BaseModel):
    id: UUID
    display_name: str
    sex: str
    surname: str | None
    surname_at_birth: str | None
    given_names: str | None
    suffix: str | None
    birth_text: str | None
    death_text: str | None
    birth_place_id: UUID | None
    death_place_id: UUID | None
    birth_place: PlaceRef | None = None
    death_place: PlaceRef | None = None
    is_living: bool
    notes_md: str | None
    status: str
    aliases: list[str] = []


class RelationshipEdge(BaseModel):
    id: UUID
    type: str
    direction: str  # "outgoing" (this person -> other) or "incoming" (other -> this)
    other: PersonRow
    confidence: int


class RelationshipsList(BaseModel):
    items: list[RelationshipEdge]


class DocumentRef(BaseModel):
    id: UUID
    title: str | None
    kind: str
    citation: str | None = None
    claim_count: int


class DocumentsList(BaseModel):
    items: list[DocumentRef]


def _row_from(p: Person, *, rel_count: int = 0, doc_count: int = 0) -> PersonRow:
    return PersonRow(
        id=p.id,
        display_name=p.display_name,
        sex=p.sex.value,
        surname=p.surname,
        given_names=p.given_names,
        birth_text=p.birth_text,
        death_text=p.death_text,
        is_living=p.is_living,
        status=p.status.value,
        relationship_count=rel_count,
        document_count=doc_count,
    )


@router.get("/people", response_model=PeopleList)
async def list_people(
    session: SessionDep,
    q: str | None = None,
    limit: int = 100,
    include_hidden: bool = False,
) -> PeopleList:
    """Listing rows include relationship + document counts so the table can
    show "12 relationships, 3 documents" without a follow-up call per row."""
    rel_subq = (
        select(Relationship.subject_id.label("pid"), func.count().label("c"))
        .where(Relationship.deleted_at.is_(None))
        .group_by(Relationship.subject_id)
        .subquery()
    )
    doc_subq = (
        select(Claim.subject_id.label("pid"), func.count(distinct(Source.document_id)).label("c"))
        .join(Source, Source.id == Claim.source_id)
        .where(Claim.subject_type == SubjectType.person, Source.document_id.is_not(None))
        .group_by(Claim.subject_id)
        .subquery()
    )

    stmt = (
        select(
            Person,
            func.coalesce(rel_subq.c.c, 0).label("rel_count"),
            func.coalesce(doc_subq.c.c, 0).label("doc_count"),
        )
        .outerjoin(rel_subq, rel_subq.c.pid == Person.id)
        .outerjoin(doc_subq, doc_subq.c.pid == Person.id)
    )

    status_filter = (
        Person.status != PersonStatus.merged
        if include_hidden
        else Person.status == PersonStatus.active
    )
    stmt = stmt.where(status_filter)

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Person.display_name.ilike(like),
                Person.surname.ilike(like),
                Person.given_names.ilike(like),
            )
        )
    stmt = stmt.order_by(Person.display_name.asc()).limit(limit)
    rows = (await session.execute(stmt)).all()
    return PeopleList(
        items=[_row_from(p, rel_count=int(rc), doc_count=int(dc)) for p, rc, dc in rows]
    )


@router.get("/people/{person_id}", response_model=PersonDetail)
async def get_person(person_id: UUID, session: SessionDep) -> PersonDetail:
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError(f"person {person_id} not found")
    aliases_stmt = select(Alias.name).where(Alias.person_id == person.id)
    aliases = list((await session.execute(aliases_stmt)).scalars().all())

    birth_place = await _place_ref(session, person.birth_place_id)
    death_place = await _place_ref(session, person.death_place_id)

    return PersonDetail(
        id=person.id,
        display_name=person.display_name,
        sex=person.sex.value,
        surname=person.surname,
        surname_at_birth=person.surname_at_birth,
        given_names=person.given_names,
        suffix=person.suffix,
        birth_text=person.birth_text,
        death_text=person.death_text,
        birth_place_id=person.birth_place_id,
        death_place_id=person.death_place_id,
        birth_place=birth_place,
        death_place=death_place,
        is_living=person.is_living,
        notes_md=person.notes_md,
        status=person.status.value,
        aliases=aliases,
    )


async def _place_ref(session: SessionDep, place_id: UUID | None) -> PlaceRef | None:
    if place_id is None:
        return None
    place = await session.get(Place, place_id)
    if place is None:
        return None
    return PlaceRef(id=place.id, name=place.name, country_code=place.country_code)


async def _ensure_place(session: SessionDep, tree_id: UUID, place_text: str | None) -> UUID | None:
    """Find a place by normalized name; create a fresh Place row if none
    matches. Used by the event-add path so user-typed places don't get
    silently dropped."""
    if not place_text:
        return None
    name = place_text.strip()
    if not name:
        return None
    normalized = normalize_place_name(name)
    existing = await session.execute(
        select(Place).where(Place.tree_id == tree_id, Place.normalized == normalized)
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return found.id
    place = Place(tree_id=tree_id, name=name, normalized=normalized)
    session.add(place)
    await session.flush()
    return place.id


@router.get("/people/{person_id}/relationships", response_model=RelationshipsList)
async def get_person_relationships(person_id: UUID, session: SessionDep) -> RelationshipsList:
    """Return every active relationship in which the person participates,
    annotated with direction so the UI can render "parent of X" vs "child of Y"
    correctly. The other-side person row is included inline."""
    other = aliased(Person)
    direction_expr = case(
        (Relationship.subject_id == person_id, "outgoing"),
        else_="incoming",
    ).label("direction")

    stmt = (
        select(Relationship, other, direction_expr)
        .join(
            other,
            other.id
            == case(
                (Relationship.subject_id == person_id, Relationship.object_id),
                else_=Relationship.subject_id,
            ),
        )
        .where(
            Relationship.deleted_at.is_(None),
            or_(
                Relationship.subject_id == person_id,
                Relationship.object_id == person_id,
            ),
        )
        .order_by(Relationship.type)
    )
    rows = (await session.execute(stmt)).all()

    items: list[RelationshipEdge] = []
    for rel, other_row, direction in rows:
        items.append(
            RelationshipEdge(
                id=rel.id,
                type=rel.type.value,
                direction=str(direction),
                other=_row_from(other_row),
                confidence=rel.confidence,
            )
        )
    return RelationshipsList(items=items)


class EventParticipantRef(BaseModel):
    person_id: UUID
    role: str
    display_name: str | None = None


class EventRow(BaseModel):
    id: UUID
    type: str
    role: str  # this person's role in the event
    date_text: str | None = None
    place: PlaceRef | None = None
    description: str | None = None
    confidence: int
    participants: list[EventParticipantRef] = []


class EventsList(BaseModel):
    items: list[EventRow]


@router.get("/people/{person_id}/events", response_model=EventsList)
async def get_person_events(person_id: UUID, session: SessionDep) -> EventsList:
    """Return every event the person participates in (births, deaths,
    marriages, divorces, censuses, etc.), with the person's role and a
    list of co-participants. Sorted ascending by date so the timeline reads
    naturally in the drawer."""
    primary_role_stmt = (
        select(EventParticipant.event_id, EventParticipant.role)
        .where(EventParticipant.person_id == person_id)
        .subquery()
    )

    event_stmt = (
        select(Event, primary_role_stmt.c.role, Place)
        .join(primary_role_stmt, primary_role_stmt.c.event_id == Event.id)
        .outerjoin(Place, Place.id == Event.place_id)
        .where(Event.deleted_at.is_(None))
        .order_by(Event.date_min.asc().nullslast(), Event.created_at.asc())
    )
    rows = (await session.execute(event_stmt)).all()

    if not rows:
        return EventsList(items=[])

    event_ids = [e.id for e, _, _ in rows]
    co_stmt = (
        select(
            EventParticipant.event_id,
            EventParticipant.person_id,
            EventParticipant.role,
            Person.display_name,
        )
        .join(Person, Person.id == EventParticipant.person_id)
        .where(EventParticipant.event_id.in_(event_ids))
    )
    co_rows = (await session.execute(co_stmt)).all()
    by_event: dict[UUID, list[EventParticipantRef]] = {}
    for ev_id, pid, role, dname in co_rows:
        by_event.setdefault(ev_id, []).append(
            EventParticipantRef(person_id=pid, role=str(role), display_name=dname)
        )

    items: list[EventRow] = []
    for event, role, place in rows:
        items.append(
            EventRow(
                id=event.id,
                type=event.type.value,
                role=str(role),
                date_text=event.date_text,
                place=PlaceRef(id=place.id, name=place.name, country_code=place.country_code)
                if place is not None
                else None,
                description=event.description,
                confidence=event.confidence,
                participants=[p for p in by_event.get(event.id, []) if p.person_id != person_id],
            )
        )
    return EventsList(items=items)


class AddEventBody(BaseModel):
    type: str  # e.g., "marriage", "birth", "divorce", etc.
    date_text: str | None = None
    place_text: str | None = None  # human-readable place name; resolved or created
    description: str | None = None
    role: str = "principal"  # this person's role
    other_participants: list[dict[str, str]] = []  # [{"person_id": "...", "role": "spouse"}]


@router.post("/people/{person_id}/events", response_model=Any)
async def add_event(
    person_id: UUID,
    body: AddEventBody,
    session: SessionDep,
) -> dict[str, str]:
    """Create + auto-approve an event proposal from the People drawer."""
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError(f"person {person_id} not found")

    try:
        EventType(body.type)
    except ValueError as e:
        raise ValidationError(f"unknown event type: {body.type}") from e

    participants: list[dict[str, str]] = [{"person_id": str(person_id), "role": body.role}]
    for p in body.other_participants:
        participants.append({"person_id": str(p["person_id"]), "role": p.get("role", "principal")})

    # Look up the place by normalized name; create a fresh Place row when
    # the user typed something we don't have yet so the event always lands
    # with a real place_id.
    place_id = await _ensure_place(session, person.tree_id, body.place_text)

    payload: dict[str, Any] = {
        "type": body.type,
        "date_text": body.date_text,
        "description": body.description,
        "participants": participants,
    }
    if place_id is not None:
        payload["place_id"] = str(place_id)

    proposal = Proposal(
        tree_id=person.tree_id,
        action=ProposalAction.create,
        target_type=SubjectType.event,
        payload_json=payload,
        rationale_md=f"{body.type.title()} added from the People drawer.",
        confidence=100,
        status=ProposalStatus.pending,
    )
    session.add(proposal)
    await session.flush()

    target_id = await apply_proposal(session, proposal, actor="user")
    proposal.status = ProposalStatus.approved
    proposal.target_id = target_id
    proposal.approved_at = utcnow()
    proposal.applied_at = utcnow()
    proposal.approved_by = "user"
    await session.flush()
    return {"proposal_id": str(proposal.id), "event_id": str(target_id)}


@router.get("/people/{person_id}/documents", response_model=DocumentsList)
async def get_person_documents(person_id: UUID, session: SessionDep) -> DocumentsList:
    """Return documents that contain at least one claim about this person.
    Counts how many claims each document contributed so the UI can
    surface high-evidence documents first."""
    stmt = (
        select(
            Document,
            Source.citation,
            func.count(Claim.id).label("claim_count"),
        )
        .join(Source, Source.document_id == Document.id)
        .join(Claim, Claim.source_id == Source.id)
        .where(
            Claim.subject_type == SubjectType.person,
            Claim.subject_id == person_id,
        )
        .group_by(Document.id, Source.citation)
        .order_by(func.count(Claim.id).desc())
    )
    rows = (await session.execute(stmt)).all()
    return DocumentsList(
        items=[
            DocumentRef(
                id=d.id,
                title=d.title,
                kind=d.kind.value,
                citation=citation,
                claim_count=int(cc),
            )
            for d, citation, cc in rows
        ]
    )


class DeletePersonResponse(BaseModel):
    proposal_id: UUID
    status: str


@router.delete("/people/{person_id}", response_model=DeletePersonResponse)
async def delete_person(person_id: UUID, session: SessionDep) -> DeletePersonResponse:
    """Soft-delete via the proposal flow so the audit trail is preserved.
    Creates an `update` proposal that flips status to hidden, then approves
    it inline since the user has already confirmed in the UI."""
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError(f"person {person_id} not found")
    if person.status == PersonStatus.hidden:
        raise ValidationError(f"person {person_id} is already hidden")

    proposal = Proposal(
        tree_id=person.tree_id,
        action=ProposalAction.delete,
        target_type=SubjectType.person,
        target_id=person.id,
        payload_json={"reason": "user_initiated"},
        rationale_md="Soft-delete requested from the People drawer.",
        confidence=100,
        status=ProposalStatus.approved,
        approved_at=utcnow(),
        applied_at=utcnow(),
        approved_by="user",
    )
    session.add(proposal)
    person.status = PersonStatus.hidden
    person.deleted_at = utcnow()
    await session.flush()
    return DeletePersonResponse(proposal_id=proposal.id, status="hidden")


class AddRelationshipBody(BaseModel):
    other_id: UUID
    type: str  # parent_of / spouse_of / sibling_of / partner_of / etc.
    direction: str = "outgoing"  # "outgoing": this -> other; "incoming": other -> this


@router.post("/people/{person_id}/relationships", response_model=Any)
async def add_relationship(
    person_id: UUID,
    body: AddRelationshipBody,
    session: SessionDep,
) -> dict[str, str]:
    """Create + auto-approve a relationship proposal from the People drawer.
    Goes through the proposal flow so the audit trail is preserved, but the
    user has already confirmed in the UI so we apply immediately."""
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError(f"person {person_id} not found")
    other = await session.get(Person, body.other_id)
    if other is None:
        raise NotFoundError(f"person {body.other_id} not found")

    if body.direction == "incoming":
        subject_id, object_id = body.other_id, person_id
    else:
        subject_id, object_id = person_id, body.other_id

    proposal = Proposal(
        tree_id=person.tree_id,
        action=ProposalAction.create,
        target_type=SubjectType.relationship,
        payload_json={
            "subject_id": str(subject_id),
            "object_id": str(object_id),
            "type": body.type,
        },
        rationale_md="Relationship added from the People drawer.",
        confidence=100,
        status=ProposalStatus.pending,
    )
    session.add(proposal)
    await session.flush()

    target_id = await apply_proposal(session, proposal, actor="user")
    proposal.status = ProposalStatus.approved
    proposal.target_id = target_id
    proposal.approved_at = utcnow()
    proposal.applied_at = utcnow()
    proposal.approved_by = "user"
    await session.flush()
    return {"proposal_id": str(proposal.id), "relationship_id": str(target_id)}


class UpdatePersonBody(BaseModel):
    """Patch a single person. Only fields present in the body are touched.
    Empty strings clear the value; null is treated as 'no change'."""

    display_name: str | None = None
    given_names: str | None = None
    surname: str | None = None
    surname_at_birth: str | None = None
    suffix: str | None = None
    sex: str | None = None
    birth_text: str | None = None
    death_text: str | None = None
    birth_place_text: str | None = None  # human-readable place name; created if new
    death_place_text: str | None = None
    is_living: bool | None = None
    notes_md: str | None = None


@router.patch("/people/{person_id}", response_model=Any)
async def update_person(
    person_id: UUID, body: UpdatePersonBody, session: SessionDep
) -> dict[str, str]:
    """Apply a field-level edit from the People drawer. Auto-approved through
    the proposal flow so each edit becomes a Claim with chat-source provenance."""
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError(f"person {person_id} not found")

    payload: dict[str, Any] = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k in {"birth_text", "death_text", "notes_md"}
    }
    if not payload:
        raise ValidationError("update body must include at least one field")

    # Resolve / create place rows for any place edits BEFORE handing the
    # payload to the applier, since the applier's _resolve_place is read-only
    # (won't conjure a new Place from a typed name).
    if payload.get("birth_place_text") is not None:
        place_id = await _ensure_place(session, person.tree_id, payload["birth_place_text"])
        if place_id is not None:
            payload["birth_place_id"] = str(place_id)
        # Always strip the *_text key so the applier doesn't double-resolve.
        payload.pop("birth_place_text", None)
    if payload.get("death_place_text") is not None:
        place_id = await _ensure_place(session, person.tree_id, payload["death_place_text"])
        if place_id is not None:
            payload["death_place_id"] = str(place_id)
        payload.pop("death_place_text", None)

    proposal = Proposal(
        tree_id=person.tree_id,
        action=ProposalAction.update,
        target_type=SubjectType.person,
        target_id=person.id,
        payload_json=payload,
        rationale_md="Field edit from the People drawer.",
        confidence=100,
        status=ProposalStatus.pending,
    )
    session.add(proposal)
    await session.flush()
    target_id = await apply_proposal(session, proposal, actor="user")
    proposal.status = ProposalStatus.approved
    proposal.target_id = target_id
    proposal.approved_at = utcnow()
    proposal.applied_at = utcnow()
    proposal.approved_by = "user"
    await session.flush()
    return {"proposal_id": str(proposal.id), "person_id": str(target_id)}


@router.delete("/relationships/{relationship_id}", response_model=Any)
async def delete_relationship(relationship_id: UUID, session: SessionDep) -> dict[str, str]:
    """Soft-delete a relationship via the proposal flow. Removes both the
    canonical row and (for symmetric types) its mirror so the edge fully
    disappears from the tree."""
    rel = await session.get(Relationship, relationship_id)
    if rel is None or rel.deleted_at is not None:
        raise NotFoundError(f"relationship {relationship_id} not found")

    proposal = Proposal(
        tree_id=rel.tree_id,
        action=ProposalAction.delete,
        target_type=SubjectType.relationship,
        target_id=rel.id,
        payload_json={"reason": "user_initiated"},
        rationale_md="Relationship removed from the People drawer.",
        confidence=100,
        status=ProposalStatus.pending,
    )
    session.add(proposal)
    await session.flush()
    await apply_proposal(session, proposal, actor="user")

    # For symmetric types, soft-delete the mirror row too so the edge is
    # gone from both directions in the relationships listing.
    if rel.type in SYMMETRIC_RELS:
        mirror_stmt = select(Relationship).where(
            Relationship.tree_id == rel.tree_id,
            Relationship.type == rel.type,
            Relationship.subject_id == rel.object_id,
            Relationship.object_id == rel.subject_id,
            Relationship.deleted_at.is_(None),
        )
        mirror = (await session.execute(mirror_stmt)).scalar_one_or_none()
        if mirror is not None:
            mirror.deleted_at = utcnow()

    proposal.status = ProposalStatus.approved
    proposal.approved_at = utcnow()
    proposal.applied_at = utcnow()
    proposal.approved_by = "user"
    await session.flush()
    return {"proposal_id": str(proposal.id), "status": "deleted"}


class AddNoteBody(BaseModel):
    notes_md: str


@router.post("/people/{person_id}/notes", response_model=Any)
async def append_note(person_id: UUID, body: AddNoteBody, session: SessionDep) -> dict[str, str]:
    """Append a free-form note to a person. Goes through the proposal flow
    (created + auto-approved) so the chat-source provenance still tracks
    the change. Existing notes are preserved with a Markdown separator."""
    person = await session.get(Person, person_id)
    if person is None:
        raise NotFoundError(f"person {person_id} not found")
    text = body.notes_md.strip()
    if not text:
        raise ValidationError("note text cannot be empty")

    new_notes = f"{person.notes_md}\n\n---\n\n{text}" if person.notes_md else text

    proposal = Proposal(
        tree_id=person.tree_id,
        action=ProposalAction.update,
        target_type=SubjectType.person,
        target_id=person.id,
        payload_json={"notes_md": new_notes},
        rationale_md="Note appended from the People drawer.",
        confidence=100,
        status=ProposalStatus.approved,
        approved_at=utcnow(),
        applied_at=utcnow(),
        approved_by="user",
    )
    session.add(proposal)
    person.notes_md = new_notes
    person.updated_at = utcnow()
    await session.flush()
    return {"proposal_id": str(proposal.id), "status": "applied"}
