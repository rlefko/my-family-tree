"""Ingestion pipeline orchestrator. Per-kind extractors feed into a uniform
sequence: extract_text -> chunk -> embed -> extract_claims -> link_claims.

Idempotent step gating uses `document.status` plus a `processing_steps` list
in `meta_json` so re-runs after a crash skip finished work."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_family_tree.core.errors import ExtractionError
from my_family_tree.core.logging import get_logger
from my_family_tree.db.session import session_scope
from my_family_tree.ingest import (
    gedcom as gedcom_extractor,
    pdf as pdf_extractor,
    text as text_extractor,
)
from my_family_tree.ingest.chunking import chunk_text
from my_family_tree.ingest.image import ocr_image
from my_family_tree.models.chunk import Chunk
from my_family_tree.models.document import Document, DocumentText
from my_family_tree.models.enums import (
    ChunkKind,
    DocumentKind,
    ExtractionMethod,
    ProcessingStatus,
)
from my_family_tree.storage.s3 import ObjectStore

log = get_logger(__name__)


PIPELINE_STEPS: tuple[str, ...] = (
    "extract_text",
    "chunk",
    "embed",
    "extract_claims",
    "link_claims",
)


@dataclass(slots=True)
class PipelineState:
    document_id: UUID
    completed_steps: list[str] = field(default_factory=list)


StepFn = Callable[[AsyncSession, Document, ObjectStore], Awaitable[None]]


async def run_pipeline(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
    storage: ObjectStore,
) -> PipelineState:
    """Run all pipeline steps for a document, skipping any already done.

    Each step is wrapped in its own transaction so a partial failure leaves
    earlier work persisted; the next attempt picks up where we left off.
    """
    state = PipelineState(document_id=document_id)

    for step_name in PIPELINE_STEPS:
        async with session_scope(session_factory) as session:
            doc = await session.get(Document, document_id)
            if doc is None:
                raise ExtractionError(f"document {document_id} disappeared mid-pipeline")
            if step_name in (doc.meta_json or {}).get("processing_steps", []):
                state.completed_steps.append(step_name)
                continue
            doc.status = _status_for(step_name)
            await session.flush()

            handler = _STEP_DISPATCH.get(step_name)
            if handler is None:
                state.completed_steps.append(step_name)
                continue
            try:
                await handler(session, doc, storage)
            except Exception as e:
                doc.attempts = (doc.attempts or 0) + 1
                doc.error = f"{step_name}: {e!s}"
                if doc.attempts >= 5:  # noqa: PLR2004
                    doc.status = ProcessingStatus.failed
                raise

            meta = dict(doc.meta_json or {})
            steps = list(meta.get("processing_steps", []))
            steps.append(step_name)
            meta["processing_steps"] = steps
            doc.meta_json = meta
            state.completed_steps.append(step_name)

    async with session_scope(session_factory) as session:
        doc = await session.get(Document, document_id)
        if doc is not None:
            doc.status = ProcessingStatus.ready
    return state


def _status_for(step: str) -> ProcessingStatus:
    return {
        "extract_text": ProcessingStatus.extracting,
        "chunk": ProcessingStatus.extracting,
        "embed": ProcessingStatus.embedding,
        "extract_claims": ProcessingStatus.extracting_claims,
        "link_claims": ProcessingStatus.extracting_claims,
    }.get(step, ProcessingStatus.pending)


# --- step handlers -----------------------------------------------------------


async def _extract_text(session: AsyncSession, doc: Document, storage: ObjectStore) -> None:
    raw = await storage.get(doc.storage_key)
    if doc.kind == DocumentKind.pdf_text:
        for page in pdf_extractor.extract_pages(raw):
            session.add(
                DocumentText(
                    document_id=doc.id,
                    page=page.page,
                    content=page.text,
                    extraction_method=ExtractionMethod.pdf_text_layer,
                )
            )
    elif doc.kind in (DocumentKind.text, DocumentKind.note):
        session.add(
            DocumentText(
                document_id=doc.id,
                page=None,
                content=text_extractor.extract_text(raw),
                extraction_method=ExtractionMethod.verbatim,
            )
        )
    elif doc.kind == DocumentKind.gedcom:
        for record in gedcom_extractor.parse(raw):
            session.add(
                DocumentText(
                    document_id=doc.id,
                    page=None,
                    content=record.rendered,
                    extraction_method=ExtractionMethod.verbatim,
                )
            )
    elif doc.kind in (DocumentKind.pdf_scan, DocumentKind.image):
        # OCR path: per-page render + tesseract / vision LLM fallback. v1 uses
        # tesseract only (vision fallback is a v2 step, gated on cost cap).
        result = ocr_image(raw)
        session.add(
            DocumentText(
                document_id=doc.id,
                page=1,
                content=result.text,
                extraction_method=ExtractionMethod.tesseract,
            )
        )
        doc.ocr_engine = result.engine


async def _chunk(session: AsyncSession, doc: Document, storage: ObjectStore) -> None:
    del storage
    stmt = select(DocumentText).where(DocumentText.document_id == doc.id)
    texts = (await session.execute(stmt)).scalars().all()
    seq_offset = 0
    for dt in texts:
        chunks = chunk_text(dt.content, page=dt.page)
        for c in chunks:
            session.add(
                Chunk(
                    document_id=doc.id,
                    document_text_id=dt.id,
                    seq=seq_offset + c.seq,
                    page=c.page,
                    start_char=c.start_char,
                    end_char=c.end_char,
                    kind=_chunk_kind(doc.kind),
                    content=c.content,
                    tokens=c.tokens,
                    meta_json={},
                )
            )
        seq_offset += len(chunks)


async def _embed(session: AsyncSession, doc: Document, storage: ObjectStore) -> None:
    """No-op stub for v1: embedding happens in a separate worker that processes
    chunks in batches. The chunk rows already exist; the embed worker fills in
    `embedding` and `embedding_half`."""
    del session, doc, storage


async def _extract_claims(session: AsyncSession, doc: Document, storage: ObjectStore) -> None:
    """No-op stub for v1. Implemented in `extract/claims.py` (separate worker)."""
    del session, doc, storage


async def _link_claims(session: AsyncSession, doc: Document, storage: ObjectStore) -> None:
    """No-op stub for v1. Implemented in `resolve/dedup.py` (separate worker)."""
    del session, doc, storage


def _chunk_kind(doc_kind: DocumentKind) -> ChunkKind:
    return {
        DocumentKind.gedcom: ChunkKind.gedcom_record,
        DocumentKind.note: ChunkKind.note,
    }.get(doc_kind, ChunkKind.prose)


_STEP_DISPATCH: dict[str, StepFn] = {
    "extract_text": _extract_text,
    "chunk": _chunk,
    "embed": _embed,
    "extract_claims": _extract_claims,
    "link_claims": _link_claims,
}


# placeholder for future API surface
_meta_unused: dict[str, Any] = {}
