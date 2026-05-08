"""Knowledge-base note tools.

The agent can save free-form research notes (`note_create`), refine them
(`note_update`), and retract them (`note_delete`). Notes ride the existing
`Document(kind=note)` plumbing so they get chunked, embedded, and surfaced via
`hybrid_search` like any other ingested content. They are NOT canonical
entities; treat these as `TRIVIAL_WRITE` so the agent can call them without a
proposal round-trip."""

from __future__ import annotations

import hashlib
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.core.errors import (
    NotFoundError,
    StorageError,
    ValidationError,
)
from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.db.session import session_scope
from my_family_tree.ingest.pipeline import PipelineDeps, run_pipeline
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.models.chunk import Chunk
from my_family_tree.models.document import Document, DocumentText
from my_family_tree.models.enums import DocumentKind, ProcessingStatus
from my_family_tree.storage.s3 import storage_key

log = get_logger(__name__)
registry = get_registry()


_NOTE_FILENAME_MAX = 500


class NoteCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=_NOTE_FILENAME_MAX)
    body: str = Field(min_length=1, max_length=200_000)


class NoteCreated(BaseModel):
    document_id: UUID
    chunk_count: int
    embedded: bool
    dedup_hit: bool


class NoteUpdateInput(BaseModel):
    document_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=_NOTE_FILENAME_MAX)
    body: str | None = Field(default=None, min_length=1, max_length=200_000)


class NoteUpdated(BaseModel):
    document_id: UUID
    chunk_count: int
    embedded: bool


class NoteDeleteInput(BaseModel):
    document_id: UUID


class NoteDeleted(BaseModel):
    document_id: UUID
    deleted: bool


def _require_storage_and_embeddings(ctx: ToolContext) -> None:
    if ctx.storage is None or ctx.embeddings is None:
        raise StorageError("notes require a configured storage backend and embeddings client")


@registry.tool(
    name="note_create",
    description=(
        "Save a free-form research note to the knowledge base. Future turns "
        "(and other tools like `hybrid_search`) can recall it. The note is "
        "stored as a Document(kind=note) and chunked + embedded inline so it "
        "is searchable as soon as the call returns. Idempotent on the body's "
        "sha256: re-creating the same body returns the existing document_id "
        "with `dedup_hit=true`."
    ),
    input_model=NoteCreateInput,
    output_model=NoteCreated,
    capability=Capability.TRIVIAL_WRITE,
    is_read_only=False,
)
async def note_create(ctx: ToolContext, payload: NoteCreateInput) -> NoteCreated:
    _require_storage_and_embeddings(ctx)
    storage = ctx.storage
    assert storage is not None  # narrowed by _require_storage_and_embeddings

    body_bytes = payload.body.encode("utf-8")
    sha256 = hashlib.sha256(body_bytes).hexdigest()

    async with session_scope(ctx.session_factory) as session:
        existing = (
            await session.execute(
                select(Document)
                .where(Document.tree_id == ctx.tree_id)
                .where(Document.sha256 == sha256)
                .where(Document.kind == DocumentKind.note)
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            chunk_count = await _count_chunks(session, existing.id)
            embedded = await _has_any_embedding(session, existing.id)
            return NoteCreated(
                document_id=existing.id,
                chunk_count=chunk_count,
                embedded=embedded,
                dedup_hit=True,
            )
        key = storage_key(str(ctx.tree_id), sha256, "txt")
        stored = await storage.put(key, body_bytes, content_type="text/plain")
        doc = Document(
            tree_id=ctx.tree_id,
            kind=DocumentKind.note,
            original_filename=payload.title[:_NOTE_FILENAME_MAX],
            mime_type="text/plain",
            byte_size=stored.size,
            sha256=sha256,
            storage_key=key,
            storage_bucket=stored.bucket,
            status=ProcessingStatus.pending,
            meta_json={"origin": "agent_note"},
        )
        session.add(doc)
        await session.flush()
        document_id = doc.id

    await run_pipeline(
        ctx.session_factory,
        document_id=document_id,
        storage=storage,
        deps=PipelineDeps(embeddings=ctx.embeddings),
    )

    async with session_scope(ctx.session_factory) as session:
        chunk_count = await _count_chunks(session, document_id)
        embedded = await _has_any_embedding(session, document_id)
    return NoteCreated(
        document_id=document_id,
        chunk_count=chunk_count,
        embedded=embedded,
        dedup_hit=False,
    )


@registry.tool(
    name="note_update",
    description=(
        "Refine an existing knowledge-base note. Pass `title` and/or `body`; "
        "the body re-hashes the storage key, drops the old chunks, and "
        "re-runs chunking and embedding so the search index reflects the "
        "new text. Use this to correct or expand a prior note rather than "
        "creating a duplicate."
    ),
    input_model=NoteUpdateInput,
    output_model=NoteUpdated,
    capability=Capability.TRIVIAL_WRITE,
    is_read_only=False,
)
async def note_update(ctx: ToolContext, payload: NoteUpdateInput) -> NoteUpdated:
    _require_storage_and_embeddings(ctx)
    storage = ctx.storage
    assert storage is not None

    if payload.title is None and payload.body is None:
        raise ValidationError("note_update requires at least one of title or body")

    document_id = payload.document_id
    new_storage_key: str | None = None

    async with session_scope(ctx.session_factory) as session:
        doc = await session.get(Document, document_id)
        if doc is None or doc.tree_id != ctx.tree_id:
            raise NotFoundError(f"note {document_id} not found")
        if doc.kind != DocumentKind.note:
            raise ValidationError(f"document {document_id} is kind={doc.kind.value}, not note")
        old_storage_key = doc.storage_key
        if payload.title is not None:
            doc.original_filename = payload.title[:_NOTE_FILENAME_MAX]
        if payload.body is not None:
            body_bytes = payload.body.encode("utf-8")
            sha256 = hashlib.sha256(body_bytes).hexdigest()
            new_storage_key = storage_key(str(ctx.tree_id), sha256, "txt")
            stored = await storage.put(new_storage_key, body_bytes, content_type="text/plain")
            doc.storage_key = new_storage_key
            doc.sha256 = sha256
            doc.byte_size = stored.size
            await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            await session.execute(
                delete(DocumentText).where(DocumentText.document_id == document_id)
            )
            meta = dict(doc.meta_json or {})
            meta["processing_steps"] = []
            doc.meta_json = meta
            doc.status = ProcessingStatus.pending
            doc.error = None
            doc.attempts = 0
            doc.processed_at = None
        doc.updated_at = utcnow()
        await session.flush()

    if new_storage_key is not None and new_storage_key != old_storage_key:
        try:
            await storage.delete(old_storage_key)
        except StorageError as e:
            # Orphaned object is harmless and the run_pipeline path below
            # still uses the new key; keep going rather than failing the
            # whole update over a janitorial issue.
            log.warning(
                "notes.storage_delete_failed",
                document_id=str(document_id),
                key=old_storage_key,
                error=str(e),
            )

    if payload.body is not None:
        await run_pipeline(
            ctx.session_factory,
            document_id=document_id,
            storage=storage,
            deps=PipelineDeps(embeddings=ctx.embeddings),
        )

    async with session_scope(ctx.session_factory) as session:
        chunk_count = await _count_chunks(session, document_id)
        embedded = await _has_any_embedding(session, document_id)
    return NoteUpdated(document_id=document_id, chunk_count=chunk_count, embedded=embedded)


@registry.tool(
    name="note_delete",
    description=(
        "Retract a knowledge-base note. The Document and its chunks are "
        "removed; the storage object is best-effort deleted. Use this when "
        "a saved note turns out to be wrong rather than overwriting it."
    ),
    input_model=NoteDeleteInput,
    output_model=NoteDeleted,
    capability=Capability.TRIVIAL_WRITE,
    is_read_only=False,
)
async def note_delete(ctx: ToolContext, payload: NoteDeleteInput) -> NoteDeleted:
    storage = ctx.storage  # may be None in stripped-down test contexts
    document_id = payload.document_id

    async with session_scope(ctx.session_factory) as session:
        doc = await session.get(Document, document_id)
        if doc is None or doc.tree_id != ctx.tree_id:
            raise NotFoundError(f"note {document_id} not found")
        if doc.kind != DocumentKind.note:
            raise ValidationError(f"document {document_id} is kind={doc.kind.value}, not note")
        old_storage_key = doc.storage_key
        await session.delete(doc)

    if storage is not None:
        try:
            await storage.delete(old_storage_key)
        except StorageError as e:
            log.warning(
                "notes.storage_delete_failed",
                document_id=str(document_id),
                key=old_storage_key,
                error=str(e),
            )
    return NoteDeleted(document_id=document_id, deleted=True)


async def _count_chunks(session: AsyncSession, document_id: UUID) -> int:
    stmt = select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
    return int((await session.execute(stmt)).scalar_one() or 0)


async def _has_any_embedding(session: AsyncSession, document_id: UUID) -> bool:
    stmt = (
        select(Chunk.id)
        .where(Chunk.document_id == document_id)
        .where(Chunk.embedding_half != None)  # noqa: E711  SQLAlchemy expects `!= None`
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None
