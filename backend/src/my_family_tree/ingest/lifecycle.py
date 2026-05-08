"""Document ingestion lifecycle helpers shared across the upload, reprocess,
and note paths so each call site does not re-implement the same SQL."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.core.time import utcnow
from my_family_tree.models.chunk import Chunk
from my_family_tree.models.document import Document, DocumentText
from my_family_tree.models.enums import ProcessingStatus

__all__ = ["count_chunks", "has_embedding", "reset_for_reingest"]


async def reset_for_reingest(session: AsyncSession, doc: Document) -> None:
    """Drop derived rows for `doc` and reset its status fields so the next
    pipeline run starts from scratch.

    Removes `Chunk` and `DocumentText` rows tied to the document, clears
    `meta_json["processing_steps"]`, and pops `meta_json["vision_calls"]`
    (a no-op for non-image kinds). Resets `status` to pending and clears
    `error`, `attempts`, and `processed_at`. Bumps `updated_at`. The caller
    is responsible for flushing and re-running or enqueueing the pipeline."""
    document_id: UUID = doc.id
    await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await session.execute(delete(DocumentText).where(DocumentText.document_id == document_id))
    meta = dict(doc.meta_json or {})
    meta["processing_steps"] = []
    meta.pop("vision_calls", None)
    doc.meta_json = meta
    doc.status = ProcessingStatus.pending
    doc.error = None
    doc.attempts = 0
    doc.processed_at = None
    doc.updated_at = utcnow()


async def count_chunks(session: AsyncSession, document_id: UUID) -> int:
    """Number of `Chunk` rows that belong to a document."""
    stmt = select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
    return int((await session.execute(stmt)).scalar_one() or 0)


async def has_embedding(session: AsyncSession, document_id: UUID) -> bool:
    """True if at least one of a document's chunks carries an embedding."""
    stmt = (
        select(Chunk.id)
        .where(Chunk.document_id == document_id)
        .where(Chunk.embedding_half != None)  # noqa: E711  SQLAlchemy expects `!= None`
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None
