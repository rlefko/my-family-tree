"""Proposal applier. Materializes a `Proposal` row into the canonical tables.

Dispatches per `(action, target_type)`. Each dispatch handler runs inside the
caller's transaction, so the API endpoint can wrap the apply + status flip in
one atomic unit. Provenance (synthetic Source + per-fact Claims) is written
on every successful person/relationship/event create or update."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.core.dates import DatePrecision, DateRange
from my_family_tree.core.errors import NotFoundError, ValidationError
from my_family_tree.core.logging import get_logger
from my_family_tree.models.claim import Claim, FactProvenance
from my_family_tree.models.conflict import Conflict
from my_family_tree.models.enums import (
    ClaimStatus,
    ConflictStatus,
    EventType,
    PersonStatus,
    ProposalAction,
    RelType,
    Sex,
    SourceKind,
    SubjectType,
)
from my_family_tree.models.event import Event, EventParticipant
from my_family_tree.models.person import Person
from my_family_tree.models.place import Place
from my_family_tree.models.proposal import Proposal
from my_family_tree.models.relationship import Relationship
from my_family_tree.models.source import Source
from my_family_tree.resolve.merge import merge_persons
from my_family_tree.services.provenance import (
    get_or_create_chat_source,
    write_user_claims,
)

log = get_logger(__name__)

SYMMETRIC_RELS: frozenset[RelType] = frozenset(
    {RelType.spouse_of, RelType.sibling_of, RelType.partner_of}
)


async def apply_proposal(  # noqa: PLR0911,PLR0912  one branch per (action, target_type) pair is the design
    session: AsyncSession,
    proposal: Any,
    *,
    actor: str,
    conversation_id: UUID | None = None,
) -> UUID | None:
    """Apply `proposal` and return the canonical target id (or None for
    operations that don't have a single id, like batch claim acceptances)."""
    payload: dict[str, Any] = proposal.payload_json or {}
    action = proposal.action
    target_type = proposal.target_type

    if action == ProposalAction.create:
        if target_type == SubjectType.person:
            return await _apply_create_person(session, proposal, payload, actor, conversation_id)
        if target_type == SubjectType.relationship:
            return await _apply_create_relationship(
                session, proposal, payload, actor, conversation_id
            )
        if target_type == SubjectType.event:
            return await _apply_create_event(session, proposal, payload, actor, conversation_id)
        if target_type == SubjectType.place:
            return await _apply_create_place(session, proposal, payload)
        if target_type is None or target_type == SubjectType.document:
            return await _apply_create_source(session, proposal, payload)

    if action == ProposalAction.update:
        if target_type == SubjectType.person:
            return await _apply_update_person(session, proposal, payload, actor, conversation_id)
        if target_type == SubjectType.event:
            return await _apply_update_event(session, proposal, payload)

    if action == ProposalAction.merge and target_type == SubjectType.person:
        return await _apply_merge_person(session, proposal, payload)

    if action == ProposalAction.delete and target_type == SubjectType.relationship:
        return await _apply_delete_relationship(session, proposal)

    if action == ProposalAction.accept_claim:
        return await _apply_accept_claim(session, proposal, actor)

    if action == ProposalAction.reject_claim:
        return await _apply_reject_claim(session, proposal)

    if action == ProposalAction.resolve_conflict:
        return await _apply_resolve_conflict(session, proposal, actor)

    raise ValidationError(f"no applier wired for (action={action}, target_type={target_type})")


# ----------------------------------------------------------------------------
# Person
# ----------------------------------------------------------------------------


async def _apply_create_person(
    session: AsyncSession,
    proposal: Any,
    payload: dict[str, Any],
    actor: str,
    conversation_id: UUID | None,
) -> UUID:
    birth = _parse_date(payload.get("birth_text"))
    death = _parse_date(payload.get("death_text"))
    birth_place_id = await _resolve_place(
        session, proposal.tree_id, payload.get("birth_place_text")
    )
    death_place_id = await _resolve_place(
        session, proposal.tree_id, payload.get("death_place_text")
    )

    person = Person(
        tree_id=proposal.tree_id,
        display_name=payload["display_name"],
        given_names=payload.get("given_names"),
        surname=payload.get("surname"),
        surname_at_birth=payload.get("surname_at_birth"),
        suffix=payload.get("suffix"),
        sex=Sex(payload.get("sex", "unknown")),
        birth_text=birth.text,
        birth_min=birth.date_min,
        birth_max=birth.date_max,
        birth_precision=int(birth.precision),
        birth_circa=birth.circa,
        birth_place_id=birth_place_id,
        death_text=death.text,
        death_min=death.date_min,
        death_max=death.date_max,
        death_precision=int(death.precision),
        death_circa=death.circa,
        death_place_id=death_place_id,
        is_living=payload.get("is_living", True),
        notes_md=payload.get("notes_md"),
        confidence=proposal.confidence,
        status=PersonStatus.active,
    )
    session.add(person)
    await session.flush()

    source = await get_or_create_chat_source(
        session,
        tree_id=proposal.tree_id,
        conversation_id=conversation_id,
    )
    facts = {
        "display_name": person.display_name,
        "given_names": person.given_names,
        "surname": person.surname,
        "sex": person.sex.value,
        "birth_text": person.birth_text,
        "birth_place_id": str(birth_place_id) if birth_place_id else None,
        "death_text": person.death_text,
        "is_living": person.is_living,
    }
    await write_user_claims(
        session,
        tree_id=proposal.tree_id,
        source=source,
        subject_type=SubjectType.person,
        subject_id=person.id,
        facts={k: v for k, v in facts.items() if v not in (None, "")},
        confidence=proposal.confidence,
        actor=actor,
    )
    return person.id


async def _apply_update_person(  # noqa: PLR0912  one branch per editable field is the design
    session: AsyncSession,
    proposal: Any,
    payload: dict[str, Any],
    actor: str,
    conversation_id: UUID | None,
) -> UUID:
    if proposal.target_id is None:
        raise ValidationError("update proposal missing target_id")
    person = await session.get(Person, proposal.target_id)
    if person is None or person.tree_id != proposal.tree_id:
        raise NotFoundError(f"person {proposal.target_id} not found")

    diff: dict[str, Any] = {}
    for field in (
        "display_name",
        "given_names",
        "surname",
        "surname_at_birth",
        "suffix",
        "is_living",
        "notes_md",
    ):
        if field in payload and payload[field] is not None:
            setattr(person, field, payload[field])
            diff[field] = payload[field]
    if "sex" in payload and payload["sex"] is not None:
        person.sex = Sex(payload["sex"])
        diff["sex"] = person.sex.value
    if "birth_text" in payload and payload["birth_text"] is not None:
        birth = _parse_date(payload["birth_text"])
        person.birth_text = birth.text
        person.birth_min = birth.date_min
        person.birth_max = birth.date_max
        person.birth_precision = int(birth.precision)
        person.birth_circa = birth.circa
        diff["birth_text"] = birth.text
    if "death_text" in payload and payload["death_text"] is not None:
        death = _parse_date(payload["death_text"])
        person.death_text = death.text
        person.death_min = death.date_min
        person.death_max = death.date_max
        person.death_precision = int(death.precision)
        person.death_circa = death.circa
        diff["death_text"] = death.text
    # Direct id (set by the People-drawer PATCH after it ensured the Place row
    # exists) takes precedence; *_text falls back to a read-only lookup.
    if payload.get("birth_place_id"):
        person.birth_place_id = UUID(str(payload["birth_place_id"]))
        diff["birth_place_id"] = str(person.birth_place_id)
    elif payload.get("birth_place_text"):
        place_id = await _resolve_place(session, proposal.tree_id, payload["birth_place_text"])
        if place_id is not None:
            person.birth_place_id = place_id
            diff["birth_place_id"] = str(place_id)
    if payload.get("death_place_id"):
        person.death_place_id = UUID(str(payload["death_place_id"]))
        diff["death_place_id"] = str(person.death_place_id)
    elif payload.get("death_place_text"):
        place_id = await _resolve_place(session, proposal.tree_id, payload["death_place_text"])
        if place_id is not None:
            person.death_place_id = place_id
            diff["death_place_id"] = str(place_id)

    person.updated_at = datetime.now(UTC)

    if diff:
        source = await get_or_create_chat_source(
            session,
            tree_id=proposal.tree_id,
            conversation_id=conversation_id,
        )
        await _supersede_claims(session, SubjectType.person, person.id, list(diff.keys()))
        await write_user_claims(
            session,
            tree_id=proposal.tree_id,
            source=source,
            subject_type=SubjectType.person,
            subject_id=person.id,
            facts=diff,
            confidence=proposal.confidence,
            actor=actor,
        )
    return person.id


async def _apply_merge_person(
    session: AsyncSession, proposal: Any, payload: dict[str, Any]
) -> UUID:
    winner_id = UUID(payload["winner_id"])
    loser_id = UUID(payload["loser_id"])
    await merge_persons(session, tree_id=proposal.tree_id, loser_id=loser_id, winner_id=winner_id)
    return winner_id


# ----------------------------------------------------------------------------
# Relationship
# ----------------------------------------------------------------------------


async def _apply_create_relationship(
    session: AsyncSession,
    proposal: Any,
    payload: dict[str, Any],
    actor: str,
    conversation_id: UUID | None,
) -> UUID:
    subject_id = await _resolve_person_ref(session, proposal.tree_id, payload["subject_id"])
    object_id = await _resolve_person_ref(session, proposal.tree_id, payload["object_id"])
    rel_type = RelType(payload["type"])

    # Idempotent: if a non-deleted relationship of the same type already
    # exists between these two persons (in either direction for symmetric
    # types), reuse it instead of inserting a duplicate. Same goes for the
    # symmetric mirror, we only add the second row if it isn't already
    # present.
    existing = await _find_existing_relationship(
        session,
        tree_id=proposal.tree_id,
        subject_id=subject_id,
        object_id=object_id,
        rel_type=rel_type,
    )
    if existing is not None:
        rel = existing
    else:
        rel = Relationship(
            tree_id=proposal.tree_id,
            subject_id=subject_id,
            object_id=object_id,
            type=rel_type,
            start_text=payload.get("start_text"),
            end_text=payload.get("end_text"),
            notes_md=payload.get("notes_md"),
            confidence=proposal.confidence,
        )
        session.add(rel)
        await session.flush()

    if rel_type in SYMMETRIC_RELS:
        mirror_existing = await _find_existing_relationship(
            session,
            tree_id=proposal.tree_id,
            subject_id=object_id,
            object_id=subject_id,
            rel_type=rel_type,
            symmetric=False,  # we want the exact reverse row, not the same one
        )
        if mirror_existing is None:
            mirror = Relationship(
                tree_id=proposal.tree_id,
                subject_id=object_id,
                object_id=subject_id,
                type=rel_type,
                start_text=payload.get("start_text"),
                end_text=payload.get("end_text"),
                notes_md=payload.get("notes_md"),
                confidence=proposal.confidence,
            )
            session.add(mirror)
            await session.flush()

    source = await get_or_create_chat_source(
        session,
        tree_id=proposal.tree_id,
        conversation_id=conversation_id,
    )
    await write_user_claims(
        session,
        tree_id=proposal.tree_id,
        source=source,
        subject_type=SubjectType.relationship,
        subject_id=rel.id,
        facts={
            "type": rel_type.value,
            "subject_id": str(subject_id),
            "object_id": str(object_id),
        },
        confidence=proposal.confidence,
        actor=actor,
    )
    return rel.id


async def _find_existing_relationship(
    session: AsyncSession,
    *,
    tree_id: UUID,
    subject_id: UUID,
    object_id: UUID,
    rel_type: RelType,
    symmetric: bool = True,
) -> Relationship | None:
    """Return an active relationship of `rel_type` between the two persons,
    or None. When `symmetric` is True (the default), matches the pair in
    either direction so we treat (A->B spouse_of) and (B->A spouse_of) as
    duplicates."""
    stmt = select(Relationship).where(
        Relationship.tree_id == tree_id,
        Relationship.type == rel_type,
        Relationship.deleted_at.is_(None),
    )
    if symmetric and rel_type in SYMMETRIC_RELS:
        stmt = stmt.where(
            ((Relationship.subject_id == subject_id) & (Relationship.object_id == object_id))
            | ((Relationship.subject_id == object_id) & (Relationship.object_id == subject_id))
        )
    else:
        stmt = stmt.where(
            Relationship.subject_id == subject_id,
            Relationship.object_id == object_id,
        )
    return (await session.execute(stmt.limit(1))).scalar_one_or_none()


async def _apply_delete_relationship(session: AsyncSession, proposal: Any) -> UUID:
    if proposal.target_id is None:
        raise ValidationError("delete proposal missing target_id")
    rel = await session.get(Relationship, proposal.target_id)
    if rel is None or rel.tree_id != proposal.tree_id:
        raise NotFoundError(f"relationship {proposal.target_id} not found")
    rel.deleted_at = datetime.now(UTC)
    return rel.id


# ----------------------------------------------------------------------------
# Event
# ----------------------------------------------------------------------------


async def _apply_create_event(
    session: AsyncSession,
    proposal: Any,
    payload: dict[str, Any],
    actor: str,
    conversation_id: UUID | None,
) -> UUID:
    date_range = _parse_date(payload.get("date_text"))
    place_id_str = payload.get("place_id")
    place_id: UUID | None = UUID(place_id_str) if place_id_str else None
    if place_id is None and payload.get("place_text"):
        place_id = await _resolve_place(session, proposal.tree_id, payload["place_text"])

    event = Event(
        tree_id=proposal.tree_id,
        type=EventType(payload["type"]),
        date_text=date_range.text,
        date_min=date_range.date_min,
        date_max=date_range.date_max,
        date_precision=int(date_range.precision),
        date_circa=date_range.circa,
        place_id=place_id,
        description=payload.get("description"),
        confidence=proposal.confidence,
    )
    session.add(event)
    await session.flush()

    for participant in payload.get("participants", []):
        person_id = await _resolve_person_ref(session, proposal.tree_id, participant["person_id"])
        session.add(
            EventParticipant(
                event_id=event.id,
                person_id=person_id,
                role=participant["role"],
            )
        )

    source = await get_or_create_chat_source(
        session,
        tree_id=proposal.tree_id,
        conversation_id=conversation_id,
    )
    await write_user_claims(
        session,
        tree_id=proposal.tree_id,
        source=source,
        subject_type=SubjectType.event,
        subject_id=event.id,
        facts={
            "type": event.type.value,
            "date_text": event.date_text,
            "place_id": str(place_id) if place_id else None,
            "description": event.description,
        },
        confidence=proposal.confidence,
        actor=actor,
    )
    return event.id


async def _apply_update_event(
    session: AsyncSession, proposal: Any, payload: dict[str, Any]
) -> UUID:
    if proposal.target_id is None:
        raise ValidationError("update event proposal missing target_id")
    event = await session.get(Event, proposal.target_id)
    if event is None or event.tree_id != proposal.tree_id:
        raise NotFoundError(f"event {proposal.target_id} not found")
    if payload.get("date_text"):
        d = _parse_date(payload["date_text"])
        event.date_text = d.text
        event.date_min = d.date_min
        event.date_max = d.date_max
        event.date_precision = int(d.precision)
        event.date_circa = d.circa
    if payload.get("place_id"):
        event.place_id = UUID(payload["place_id"])
    if payload.get("description"):
        event.description = payload["description"]
    event.updated_at = datetime.now(UTC)
    return event.id


# ----------------------------------------------------------------------------
# Place
# ----------------------------------------------------------------------------


async def _apply_create_place(
    session: AsyncSession, proposal: Any, payload: dict[str, Any]
) -> UUID:
    name: str = payload["name"]
    normalized = normalize_place_name(name)
    existing = await _find_existing_place(session, proposal.tree_id, normalized)
    if existing is not None:
        raise ValidationError(
            f"place '{name}' looks like an existing place: {existing.id}; merge or update instead"
        )
    parent = payload.get("parent_place_id")
    place = Place(
        tree_id=proposal.tree_id,
        name=name,
        normalized=normalized,
        country_code=payload.get("country_code"),
        admin1=payload.get("admin1"),
        admin2=payload.get("admin2"),
        locality=payload.get("locality"),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        parent_place_id=UUID(parent) if parent else None,
    )
    session.add(place)
    await session.flush()
    return place.id


async def _resolve_place(
    session: AsyncSession, tree_id: UUID, place_text: str | None
) -> UUID | None:
    """Look up a place by normalized name. v1 doesn't auto-create the place
    if missing; the chat agent should propose one separately."""
    if not place_text:
        return None
    normalized = normalize_place_name(place_text)
    found = await _find_existing_place(session, tree_id, normalized)
    return found.id if found else None


async def _find_existing_place(
    session: AsyncSession, tree_id: UUID, normalized: str
) -> Place | None:
    stmt = select(Place).where(
        Place.tree_id == tree_id,
        Place.normalized == normalized,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def normalize_place_name(name: str) -> str:
    return name.strip().lower()


# ----------------------------------------------------------------------------
# Source / claim / conflict
# ----------------------------------------------------------------------------


async def _apply_create_source(
    session: AsyncSession, proposal: Any, payload: dict[str, Any]
) -> UUID:
    source = Source(
        tree_id=proposal.tree_id,
        kind=SourceKind(payload["kind"]),
        title=payload["title"],
        repository=payload.get("repository"),
        citation=payload.get("citation"),
        url=payload.get("url"),
        document_id=UUID(payload["document_id"]) if payload.get("document_id") else None,
        meta_json=payload.get("meta_json", {}),
    )
    session.add(source)
    await session.flush()
    return source.id


async def _apply_accept_claim(session: AsyncSession, proposal: Any, actor: str) -> UUID:
    if proposal.target_id is None:
        raise ValidationError("accept_claim proposal missing target_id (claim_id)")
    claim = await session.get(Claim, proposal.target_id)
    if claim is None or claim.tree_id != proposal.tree_id:
        raise NotFoundError(f"claim {proposal.target_id} not found")
    claim.status = ClaimStatus.accepted
    claim.accepted_at = datetime.now(UTC)
    claim.accepted_by = actor
    session.add(
        FactProvenance(
            subject_type=claim.subject_type,
            subject_id=claim.subject_id,
            predicate=claim.predicate,
            claim_id=claim.id,
        )
    )
    return claim.id


async def _apply_reject_claim(session: AsyncSession, proposal: Any) -> UUID:
    if proposal.target_id is None:
        raise ValidationError("reject_claim proposal missing target_id (claim_id)")
    claim = await session.get(Claim, proposal.target_id)
    if claim is None or claim.tree_id != proposal.tree_id:
        raise NotFoundError(f"claim {proposal.target_id} not found")
    claim.status = ClaimStatus.rejected
    return claim.id


async def _apply_resolve_conflict(session: AsyncSession, proposal: Any, actor: str) -> UUID:
    if proposal.target_id is None:
        raise ValidationError("resolve_conflict proposal missing target_id (conflict_id)")
    conflict = await session.get(Conflict, proposal.target_id)
    if conflict is None or conflict.tree_id != proposal.tree_id:
        raise NotFoundError(f"conflict {proposal.target_id} not found")
    conflict.status = ConflictStatus.resolved
    conflict.resolved_at = datetime.now(UTC)
    conflict.resolved_by = actor
    return conflict.id


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


async def _resolve_person_ref(session: AsyncSession, tree_id: UUID, raw: str | UUID) -> UUID:
    """A relationship or event participant can reference a person either by
    their canonical `person.id` (if the person already exists) or by the
    `proposal_id` of a still-pending or recently-applied person create proposal
    in the same batch (since the agent wires up edges in the same turn it
    proposes the people, before the user has approved anything).

    We try the canonical row first, then fall back to looking up the proposal
    and using its `target_id`. Either yields a real person id; if neither
    resolves, we raise NotFoundError so the failure surfaces on the user's
    Approve click rather than later as a constraint violation."""
    pid = UUID(str(raw))
    person = await session.get(Person, pid)
    if person is not None and person.tree_id == tree_id:
        # Follow merge redirects so we never edge to a tombstoned row.
        while person.status == PersonStatus.merged and person.merged_into_id is not None:
            target = await session.get(Person, person.merged_into_id)
            if target is None:
                break
            person = target
        return person.id

    proposal = await session.get(Proposal, pid)
    if (
        proposal is not None
        and proposal.tree_id == tree_id
        and proposal.target_type == SubjectType.person
        and proposal.action == ProposalAction.create
        and proposal.target_id is not None
    ):
        return proposal.target_id

    raise NotFoundError(
        f"person reference {pid} did not resolve to a canonical person or applied "
        f"create-person proposal in tree {tree_id}"
    )


def _parse_date(text: str | None) -> DateRange:
    if not text:
        return DateRange(precision=DatePrecision.UNKNOWN)
    return DateRange.from_text(text)


async def _supersede_claims(
    session: AsyncSession,
    subject_type: SubjectType,
    subject_id: UUID,
    predicates: list[str],
) -> None:
    """Mark prior accepted claims for these predicates as superseded so the new
    claim becomes the canonical source."""
    if not predicates:
        return
    stmt = select(Claim).where(
        Claim.subject_type == subject_type,
        Claim.subject_id == subject_id,
        Claim.predicate.in_(predicates),
        Claim.status == ClaimStatus.accepted,
    )
    rows = (await session.execute(stmt)).scalars().all()
    for claim in rows:
        claim.status = ClaimStatus.superseded
