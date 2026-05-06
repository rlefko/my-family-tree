"""Document endpoints: list, upload, get."""

from __future__ import annotations

import hashlib
import mimetypes
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from my_family_tree.api.deps import SessionDep, StorageDep
from my_family_tree.ingest.pdf import has_text_layer
from my_family_tree.models.document import Document
from my_family_tree.models.enums import DocumentKind, ProcessingStatus
from my_family_tree.storage.s3 import storage_key

router = APIRouter()


class DocumentCreated(BaseModel):
    document_id: UUID
    sha256: str
    kind: DocumentKind
    status: ProcessingStatus


class DocumentRow(BaseModel):
    id: UUID
    kind: str
    original_filename: str
    status: str
    pages: int | None = None


class DocumentList(BaseModel):
    items: list[DocumentRow]


@router.get("/documents", response_model=DocumentList)
async def list_documents(
    session: SessionDep,
    limit: int = 50,
) -> DocumentList:
    stmt = select(Document).order_by(Document.imported_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return DocumentList(
        items=[
            DocumentRow(
                id=d.id,
                kind=d.kind.value,
                original_filename=d.original_filename,
                status=d.status.value,
                pages=d.pages,
            )
            for d in rows
        ]
    )


@router.post("/documents", response_model=DocumentCreated, status_code=201)
async def upload_document(
    session: SessionDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
    tree_id: Annotated[UUID, Form()],
    kind: Annotated[DocumentKind | None, Form()] = None,
) -> DocumentCreated:
    data = await file.read()
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
        raise HTTPException(status_code=500, detail="document_id not generated")
    return DocumentCreated(
        document_id=doc.id, sha256=sha256, kind=detected_kind, status=ProcessingStatus.pending
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
