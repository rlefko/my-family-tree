"""Document + DocumentText.

Documents are the raw uploads (PDFs, images, GEDCOM, text). DocumentText is the
extracted plain text per page (one row per page; non-paginated docs use page=None).
Chunks live in their own table because they carry vector embeddings and FTS."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, SQLModel

from my_family_tree.models._columns import (
    bigint_column,
    created_at_column,
    enum_column,
    fk_column,
    int_column,
    jsonb_column,
    pk_column,
    soft_delete_column,
    text_column,
    updated_at_column,
)
from my_family_tree.models.enums import DocumentKind, ExtractionMethod, ProcessingStatus


class Document(SQLModel, table=True):
    __tablename__ = "document"

    id: UUID = pk_column()
    tree_id: UUID = fk_column("tree.id", ondelete="CASCADE")
    kind: DocumentKind = enum_column(DocumentKind, "document_kind", nullable=False, index=True)

    original_filename: str = Field(max_length=500, nullable=False)
    mime_type: str = Field(max_length=120, nullable=False)
    byte_size: int = bigint_column(nullable=False, default=0)

    sha256: str = Field(
        sa_column=Column(String(length=64), nullable=False, index=True),
    )

    storage_key: str = Field(max_length=600, nullable=False)
    storage_bucket: str = Field(max_length=200, nullable=False)

    status: ProcessingStatus = enum_column(
        ProcessingStatus,
        "processing_status",
        nullable=False,
        default=ProcessingStatus.pending,
        index=True,
    )
    pages: int | None = int_column()
    language: str | None = Field(
        default=None,
        sa_column=Column(String(length=8), nullable=True),
    )
    ocr_engine: str | None = text_column()

    imported_at: datetime = created_at_column()
    processed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    error: str | None = text_column()
    attempts: int = int_column(nullable=False, default=0)
    meta_json: dict = jsonb_column(nullable=False, default=dict)

    created_at: datetime = created_at_column()
    updated_at: datetime = updated_at_column()
    deleted_at: datetime | None = soft_delete_column()


class DocumentText(SQLModel, table=True):
    __tablename__ = "document_text"

    id: UUID = pk_column()
    document_id: UUID = fk_column("document.id", ondelete="CASCADE")
    page: int | None = int_column()
    content: str = text_column(nullable=False)
    extraction_method: ExtractionMethod = enum_column(
        ExtractionMethod, "extraction_method", nullable=False
    )

    created_at: datetime = created_at_column()
