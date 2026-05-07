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
    PersonStatus,
    ProposalAction,
    ProposalStatus,
    SubjectType,
)
from my_family_tree.models.person import Alias, Person
from my_family_tree.models.proposal import Proposal
from my_family_tree.models.relationship import Relationship
from my_family_tree.models.source import Source
from my_family_tree.services.proposal_apply import apply_proposal

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
        is_living=person.is_living,
        notes_md=person.notes_md,
        status=person.status.value,
        aliases=aliases,
    )


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
