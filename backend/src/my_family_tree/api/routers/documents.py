"""Document endpoints: list, upload, detail, raw, download, text, chunks,
delete, reprocess. Ingest is enqueued via the arq pool on upload."""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.sql import nulls_last

from my_family_tree.api.deps import EnqueueDep, SessionDep, SettingsDep, StorageDep
from my_family_tree.core.errors import (
    NotFoundError,
    RequestTooLargeError,
    StorageError,
)
from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.ingest.pdf import has_text_layer
from my_family_tree.models.chunk import Chunk
from my_family_tree.models.document import Document, DocumentText
from my_family_tree.models.enums import DocumentKind, ProcessingStatus
from my_family_tree.models.source import Source
from my_family_tree.storage.s3 import storage_key

router = APIRouter()
log = get_logger(__name__)


class DocumentRow(BaseModel):
    id: UUID
    kind: str
    original_filename: str
    status: str
    pages: int | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None
    error: str | None = None


class DocumentList(BaseModel):
    items: list[DocumentRow]
    total: int


class DocumentCreated(BaseModel):
    document_id: UUID
    sha256: str
    kind: DocumentKind
    status: ProcessingStatus


class DocumentDetail(BaseModel):
    id: UUID
    kind: str
    mime_type: str
    byte_size: int
    sha256: str
    original_filename: str
    status: str
    pages: int | None = None
    language: str | None = None
    ocr_engine: str | None = None
    error: str | None = None
    attempts: int = 0
    imported_at: datetime
    processed_at: datetime | None = None
    text_count: int
    chunk_count: int
    vision_calls: list[dict[str, Any]] = []


class DocumentTextRow(BaseModel):
    id: UUID
    page: int | None
    extraction_method: str
    content: str
    created_at: datetime


class DocumentTextList(BaseModel):
    items: list[DocumentTextRow]
    total: int


class ChunkRow(BaseModel):
    id: UUID
    seq: int
    page: int | None
    kind: str
    tokens: int
    content: str
    embedded: bool


class ChunkList(BaseModel):
    items: list[ChunkRow]
    total: int


class DocumentDeleted(BaseModel):
    id: UUID
    deleted: bool
    orphaned_sources_count: int


class DocumentReprocessed(BaseModel):
    id: UUID
    status: str
    job_id: str | None


@router.get("/documents", response_model=DocumentList)
async def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    kind: Annotated[DocumentKind | None, Query()] = None,
    status: Annotated[ProcessingStatus | None, Query()] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> DocumentList:
    base = select(Document)
    count_stmt = select(func.count()).select_from(Document)
    if kind is not None:
        base = base.where(Document.kind == kind)
        count_stmt = count_stmt.where(Document.kind == kind)
    if status is not None:
        base = base.where(Document.status == status)
        count_stmt = count_stmt.where(Document.status == status)
    if q:
        like = f"%{q}%"
        base = base.where(
            or_(Document.original_filename.ilike(like), Document.mime_type.ilike(like))
        )
        count_stmt = count_stmt.where(
            or_(Document.original_filename.ilike(like), Document.mime_type.ilike(like))
        )
    base = base.order_by(Document.imported_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(base)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return DocumentList(
        items=[
            DocumentRow(
                id=d.id,
                kind=d.kind.value,
                original_filename=d.original_filename,
                status=d.status.value,
                pages=d.pages,
                mime_type=d.mime_type,
                size_bytes=d.byte_size,
                created_at=d.created_at,
                processed_at=d.processed_at,
                error=d.error,
            )
            for d in rows
        ],
        total=int(total),
    )


@router.post("/documents", response_model=DocumentCreated, status_code=201)
async def upload_document(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    pool: EnqueueDep,
    file: Annotated[UploadFile, File()],
    tree_id: Annotated[UUID, Form()],
    kind: Annotated[DocumentKind | None, Form()] = None,
) -> DocumentCreated:
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise RequestTooLargeError(
            f"file exceeds max upload size of {settings.max_upload_bytes} bytes"
        )
    sha256 = hashlib.sha256(data).hexdigest()

    existing = await session.execute(
        select(Document).where(Document.tree_id == tree_id, Document.sha256 == sha256)
    )
    found = existing.scalar_one_or_none()
    if found is not None:
        return DocumentCreated(
            document_id=found.id, sha256=sha256, kind=found.kind, status=found.status
        )

    detected_kind = kind or _detect_kind(file.filename or "", file.content_type or "", data)
    ext = (file.filename or "").rsplit(".", 1)[-1] if "." in (file.filename or "") else ""
    key = storage_key(str(tree_id), sha256, ext)
    await storage.put(key, data, content_type=file.content_type or "application/octet-stream")

    doc = Document(
        tree_id=tree_id,
        kind=detected_kind,
        original_filename=file.filename or "upload",
        mime_type=file.content_type or "application/octet-stream",
        byte_size=len(data),
        sha256=sha256,
        storage_key=key,
        storage_bucket=storage.bucket,
        status=ProcessingStatus.pending,
        meta_json={},
    )
    session.add(doc)
    await session.flush()
    if doc.id is None:
        raise StorageError("document_id not generated")
    job = await pool.enqueue_job("ingest_document", str(doc.id))
    log.info("documents.enqueued", document_id=str(doc.id), job_id=str(job.job_id) if job else None)
    return DocumentCreated(
        document_id=doc.id, sha256=sha256, kind=detected_kind, status=ProcessingStatus.pending
    )


@router.get("/documents/{document_id}", response_model=DocumentDetail)
async def get_document(session: SessionDep, document_id: UUID) -> DocumentDetail:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    text_count = (
        await session.execute(
            select(func.count()).select_from(DocumentText).where(DocumentText.document_id == doc.id)
        )
    ).scalar_one()
    chunk_count = (
        await session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
        )
    ).scalar_one()
    return DocumentDetail(
        id=doc.id,
        kind=doc.kind.value,
        mime_type=doc.mime_type,
        byte_size=doc.byte_size,
        sha256=doc.sha256,
        original_filename=doc.original_filename,
        status=doc.status.value,
        pages=doc.pages,
        language=doc.language,
        ocr_engine=doc.ocr_engine,
        error=doc.error,
        attempts=doc.attempts or 0,
        imported_at=doc.imported_at,
        processed_at=doc.processed_at,
        text_count=int(text_count),
        chunk_count=int(chunk_count),
        vision_calls=list((doc.meta_json or {}).get("vision_calls", [])),
    )


@router.get("/documents/{document_id}/raw")
async def stream_document_raw(
    session: SessionDep, storage: StorageDep, document_id: UUID
) -> StreamingResponse:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    return StreamingResponse(
        storage.stream(doc.storage_key),
        media_type=doc.mime_type,
        headers={"Content-Length": str(doc.byte_size)},
    )


@router.get("/documents/{document_id}/download")
async def download_document(
    session: SessionDep, storage: StorageDep, document_id: UUID
) -> StreamingResponse:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    safe_name = (doc.original_filename or "download").replace('"', "_")
    return StreamingResponse(
        storage.stream(doc.storage_key),
        media_type=doc.mime_type,
        headers={
            "Content-Length": str(doc.byte_size),
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )


@router.get("/documents/{document_id}/text", response_model=DocumentTextList)
async def list_document_text(
    session: SessionDep,
    document_id: UUID,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    page: Annotated[int | None, Query(ge=1)] = None,
) -> DocumentTextList:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    base = select(DocumentText).where(DocumentText.document_id == document_id)
    count_stmt = (
        select(func.count())
        .select_from(DocumentText)
        .where(DocumentText.document_id == document_id)
    )
    if page is not None:
        base = base.where(DocumentText.page == page)
        count_stmt = count_stmt.where(DocumentText.page == page)
    base = (
        base.order_by(nulls_last(DocumentText.page.asc()), DocumentText.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(base)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return DocumentTextList(
        items=[
            DocumentTextRow(
                id=t.id,
                page=t.page,
                extraction_method=t.extraction_method.value,
                content=t.content,
                created_at=t.created_at,
            )
            for t in rows
        ],
        total=int(total),
    )


@router.get("/documents/{document_id}/chunks", response_model=ChunkList)
async def list_document_chunks(
    session: SessionDep,
    document_id: UUID,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    page: Annotated[int | None, Query(ge=1)] = None,
) -> ChunkList:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    base = select(Chunk).where(Chunk.document_id == document_id)
    count_stmt = select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
    if page is not None:
        base = base.where(Chunk.page == page)
        count_stmt = count_stmt.where(Chunk.page == page)
    base = base.order_by(Chunk.seq.asc()).limit(limit).offset(offset)
    rows = (await session.execute(base)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return ChunkList(
        items=[
            ChunkRow(
                id=c.id,
                seq=c.seq,
                page=c.page,
                kind=c.kind.value,
                tokens=c.tokens,
                content=c.content,
                embedded=c.embedding is not None,
            )
            for c in rows
        ],
        total=int(total),
    )


@router.delete("/documents/{document_id}", response_model=DocumentDeleted)
async def delete_document(
    session: SessionDep, storage: StorageDep, document_id: UUID
) -> DocumentDeleted:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
    orphaned = (
        await session.execute(
            select(func.count()).select_from(Source).where(Source.document_id == document_id)
        )
    ).scalar_one()
    try:
        await storage.delete(doc.storage_key)
    except StorageError as e:
        log.warning("documents.storage_delete_failed", document_id=str(document_id), error=str(e))
    await session.delete(doc)
    return DocumentDeleted(id=document_id, deleted=True, orphaned_sources_count=int(orphaned))


@router.post("/documents/{document_id}/reprocess", response_model=DocumentReprocessed)
async def reprocess_document(
    session: SessionDep, pool: EnqueueDep, document_id: UUID
) -> DocumentReprocessed:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"document {document_id} not found")
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
    await session.flush()
    job = await pool.enqueue_job("ingest_document", str(document_id))
    return DocumentReprocessed(
        id=document_id,
        status=ProcessingStatus.pending.value,
        job_id=str(job.job_id) if job else None,
    )


def _detect_kind(filename: str, content_type: str, data: bytes) -> DocumentKind:
    lower = filename.lower()
    if lower.endswith(".ged") or content_type == "application/x-gedcom":
        return DocumentKind.gedcom
    if lower.endswith(".pdf") or content_type == "application/pdf":
        return _pdf_kind(data)
    guessed, _ = mimetypes.guess_type(filename)
    ct = content_type or guessed or ""
    if ct.startswith("image/"):
        return DocumentKind.image
    if ct.startswith("text/"):
        return DocumentKind.text
    return DocumentKind.text


def _pdf_kind(data: bytes) -> DocumentKind:
    """Probe whether the PDF has a text layer to decide pdf_text vs pdf_scan."""
    try:
        return DocumentKind.pdf_text if has_text_layer(data) else DocumentKind.pdf_scan
    except Exception:
        return DocumentKind.pdf_text
