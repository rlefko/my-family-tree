"""Chunks: searchable units of text from a document.

Carries:
- `embedding` (vector(3072)): full-precision canonical value (kept for re-index).
- `embedding_half` (halfvec(3072)): the column actually queried (HNSW-indexable).
- `tsv` (tsvector): generated FTS column (created in the migration).
- `meta_json`: GEDCOM tag path, table coords, vision-LLM bbox, etc.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from my_family_tree.db.types import HALFVEC, Vector
from my_family_tree.models._columns import (
    created_at_column,
    enum_column,
    fk_column,
    int_column,
    jsonb_column,
    pk_column,
    text_column,
)
from my_family_tree.models.enums import ChunkKind


class Chunk(SQLModel, table=True):
    __tablename__ = "chunk"

    id: UUID = pk_column()
    document_id: UUID = fk_column("document.id", ondelete="CASCADE")
    document_text_id: UUID | None = fk_column(
        "document_text.id", ondelete="SET NULL", nullable=True
    )

    seq: int = int_column(nullable=False, default=0)
    page: int | None = int_column()
    start_char: int = int_column(nullable=False, default=0)
    end_char: int = int_column(nullable=False, default=0)

    kind: ChunkKind = enum_column(
        ChunkKind, "chunk_kind", nullable=False, default=ChunkKind.prose, index=True
    )
    content: str = text_column(nullable=False)
    tokens: int = int_column(nullable=False, default=0)

    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(3072), nullable=True),
    )
    embedding_half: list[float] | None = Field(
        default=None,
        sa_column=Column(HALFVEC(3072), nullable=True),
    )

    meta_json: dict = jsonb_column(nullable=False, default=dict)

    created_at: datetime = created_at_column()
