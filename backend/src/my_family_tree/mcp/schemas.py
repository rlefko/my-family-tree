"""Pydantic models shared across MCP tool inputs/outputs. Keep this file
small; per-tool ad-hoc schemas live in their own module under `mcp/tools/`."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IdRef(BaseModel):
    id: UUID


class Pagination(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class DateRangeOut(BaseModel):
    text: str | None = None
    min: date | None = None
    max: date | None = None
    precision: int = 0
    circa: bool = False


class PersonSummary(BaseModel):
    id: UUID
    display_name: str
    sex: str
    birth: DateRangeOut
    death: DateRangeOut
    confidence: int


class PersonDetail(PersonSummary):
    given_names: str | None = None
    surname: str | None = None
    surname_at_birth: str | None = None
    notes_md: str | None = None
    aliases: list[str] = Field(default_factory=list)


class PlaceSummary(BaseModel):
    id: UUID
    name: str
    normalized: str
    country_code: str | None = None
    admin1: str | None = None
    admin2: str | None = None


class EventSummary(BaseModel):
    id: UUID
    type: str
    date: DateRangeOut
    place_id: UUID | None = None
    description: str | None = None
    confidence: int


class DocumentSummary(BaseModel):
    id: UUID
    kind: str
    original_filename: str
    status: str
    pages: int | None = None
    created_at: datetime


class ConflictSummary(BaseModel):
    id: UUID
    kind: str
    status: str
    severity: int
    summary: str
    subject_id: UUID
    subject_type: str


class ProposalRef(BaseModel):
    proposal_id: UUID
    rationale: str
    confidence: int = 50


class TreeStats(BaseModel):
    persons: int
    events: int
    relationships: int
    documents: int
    conflicts_open: int
    proposals_pending: int


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    page: int | None = None
    content: str
    score: float
