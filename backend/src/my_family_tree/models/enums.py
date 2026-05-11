"""Postgres ENUM types. One source of truth; migrations create these as
real Postgres enums and models reference them with `create_type=False`."""

from __future__ import annotations

from enum import StrEnum


class Sex(StrEnum):
    male = "male"
    female = "female"
    unknown = "unknown"


class PersonStatus(StrEnum):
    active = "active"
    merged = "merged"
    hidden = "hidden"


class RelType(StrEnum):
    parent_of = "parent_of"
    spouse_of = "spouse_of"
    sibling_of = "sibling_of"
    adoptive_parent_of = "adoptive_parent_of"
    step_parent_of = "step_parent_of"
    guardian_of = "guardian_of"
    partner_of = "partner_of"


SYMMETRIC_REL_TYPES: frozenset[RelType] = frozenset(
    {RelType.spouse_of, RelType.sibling_of, RelType.partner_of}
)


class EventType(StrEnum):
    birth = "birth"
    death = "death"
    baptism = "baptism"
    burial = "burial"
    marriage = "marriage"
    divorce = "divorce"
    immigration = "immigration"
    emigration = "emigration"
    residence = "residence"
    census = "census"
    military = "military"
    occupation = "occupation"
    education = "education"
    religion = "religion"
    will = "will"
    probate = "probate"
    other = "other"


class EventRole(StrEnum):
    principal = "principal"
    spouse = "spouse"
    father = "father"
    mother = "mother"
    witness = "witness"
    officiant = "officiant"
    informant = "informant"
    deceased = "deceased"


class DocumentKind(StrEnum):
    pdf_text = "pdf_text"
    pdf_scan = "pdf_scan"
    image = "image"
    text = "text"
    gedcom = "gedcom"
    note = "note"
    web = "web"


class ProcessingStatus(StrEnum):
    pending = "pending"
    extracting = "extracting"
    embedding = "embedding"
    extracting_claims = "extracting_claims"
    ready = "ready"
    failed = "failed"


class ExtractionMethod(StrEnum):
    pdf_text_layer = "pdf_text_layer"
    tesseract = "tesseract"
    vision_llm = "vision_llm"
    verbatim = "verbatim"


class ChunkKind(StrEnum):
    prose = "prose"
    table_row = "table_row"
    gedcom_record = "gedcom_record"
    note = "note"


class SourceKind(StrEnum):
    vital_record = "vital_record"
    census = "census"
    newspaper = "newspaper"
    obituary = "obituary"
    church = "church"
    immigration = "immigration"
    military = "military"
    cemetery = "cemetery"
    dna = "dna"
    family_oral = "family_oral"
    user_assertion = "user_assertion"
    other = "other"


class ClaimKind(StrEnum):
    person_attr = "person_attr"
    event = "event"
    relationship = "relationship"
    alias = "alias"
    residence = "residence"
    source_link = "source_link"


class ClaimStatus(StrEnum):
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"
    superseded = "superseded"


class SubjectType(StrEnum):
    person = "person"
    event = "event"
    relationship = "relationship"
    place = "place"
    document = "document"


class ConflictKind(StrEnum):
    date_mismatch = "date_mismatch"
    place_mismatch = "place_mismatch"
    parentage_mismatch = "parentage_mismatch"
    duplicate_person = "duplicate_person"
    sex_mismatch = "sex_mismatch"
    impossible_age = "impossible_age"
    circular_lineage = "circular_lineage"
    multiple_spouses_same_time = "multiple_spouses_same_time"


class ConflictStatus(StrEnum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class ConflictPosition(StrEnum):
    a = "a"
    b = "b"
    evidence_for_a = "evidence_for_a"
    evidence_for_b = "evidence_for_b"
    context = "context"


class ProposalAction(StrEnum):
    create = "create"
    update = "update"
    delete = "delete"
    merge = "merge"
    accept_claim = "accept_claim"
    reject_claim = "reject_claim"
    resolve_conflict = "resolve_conflict"


class ProposalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    canceled = "canceled"


class MessageRole(StrEnum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"


class AgentRole(StrEnum):
    chat = "chat"
    deep_research = "deep_research"
    conflict_resolver = "conflict_resolver"
    dedup = "dedup"


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    needs_input = "needs_input"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# Convenience: mapping enum -> Postgres type name (used in migration).
ENUMS = {
    "sex": Sex,
    "person_status": PersonStatus,
    "rel_type": RelType,
    "event_type": EventType,
    "event_role": EventRole,
    "document_kind": DocumentKind,
    "processing_status": ProcessingStatus,
    "extraction_method": ExtractionMethod,
    "chunk_kind": ChunkKind,
    "source_kind": SourceKind,
    "claim_kind": ClaimKind,
    "claim_status": ClaimStatus,
    "subject_type": SubjectType,
    "conflict_kind": ConflictKind,
    "conflict_status": ConflictStatus,
    "conflict_position": ConflictPosition,
    "proposal_action": ProposalAction,
    "proposal_status": ProposalStatus,
    "message_role": MessageRole,
    "agent_role": AgentRole,
    "run_status": RunStatus,
}
