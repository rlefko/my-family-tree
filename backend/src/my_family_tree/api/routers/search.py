"""Search endpoint: hybrid (vector + FTS via RRF) over chunks. The server
embeds the query so the frontend never sees the embeddings model."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from my_family_tree.api.deps import EmbeddingsDep, SessionDep
from my_family_tree.retrieve.hybrid import hybrid_search

router = APIRouter()


class ChunkSearchRequest(BaseModel):
    tree_id: UUID
    query: Annotated[str, Field(min_length=1, max_length=500)]
    k: Annotated[int, Field(ge=1, le=50)] = 10
    document_id: UUID | None = None


class ChunkSearchHit(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_filename: str | None
    document_kind: str | None
    page: int | None
    content: str
    score: float


class ChunkSearchResponse(BaseModel):
    items: list[ChunkSearchHit]


@router.post("/search/chunks", response_model=ChunkSearchResponse)
async def search_chunks(
    session: SessionDep, embeddings: EmbeddingsDep, req: ChunkSearchRequest
) -> ChunkSearchResponse:
    vectors = await embeddings.embed([req.query])
    embedding = vectors[0] if vectors else None
    hits = await hybrid_search(
        session,
        tree_id=req.tree_id,
        query=req.query,
        embedding=embedding,
        k=req.k,
        document_id=req.document_id,
    )
    return ChunkSearchResponse(
        items=[
            ChunkSearchHit(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_filename=h.document_filename,
                document_kind=h.document_kind,
                page=h.page,
                content=h.content,
                score=h.score,
            )
            for h in hits
        ]
    )
