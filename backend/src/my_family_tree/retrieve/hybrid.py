"""Hybrid retrieval: vector + FTS via Reciprocal Rank Fusion."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.models.chunk import Chunk
from my_family_tree.models.document import Document


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    page: int | None
    content: str
    score: float


async def hybrid_search(
    session: AsyncSession,
    *,
    tree_id: UUID,
    query: str,
    embedding: list[float] | None = None,
    k: int = 10,
    k_rrf: int = 60,
) -> list[RetrievedChunk]:
    """Run an RRF-fused hybrid search. Caller provides an embedding; this
    function does not call the embeddings client itself, so it can be used
    in cost-sensitive or offline contexts."""
    fts_stmt = text(
        """
        SELECT chunk.id AS chunk_id,
               chunk.document_id,
               chunk.page,
               chunk.content,
               ts_rank_cd(chunk.tsv, plainto_tsquery('english', :q)) AS rank
          FROM chunk
          JOIN document ON document.id = chunk.document_id
         WHERE document.tree_id = :tree_id
           AND chunk.tsv @@ plainto_tsquery('english', :q)
         ORDER BY rank DESC
         LIMIT :k3
        """
    )
    fts_rows = (
        (await session.execute(fts_stmt, {"q": query, "tree_id": tree_id, "k3": k * 3}))
        .mappings()
        .all()
    )

    scores: dict[UUID, float] = {}
    sources: dict[UUID, dict] = {}
    for rank, row in enumerate(fts_rows, start=1):
        cid = row["chunk_id"]
        sources[cid] = dict(row)
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k_rrf + rank)

    if embedding is not None:
        distance = Chunk.embedding_half.op("<=>")(embedding).label("distance")
        vec_stmt = (
            select(Chunk, distance)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.tree_id == tree_id)
            .order_by(distance.asc())
            .limit(k * 3)
        )
        vec_rows = (await session.execute(vec_stmt)).all()
        for rank, row in enumerate(vec_rows, start=1):
            cid = row.Chunk.id
            sources.setdefault(
                cid,
                {
                    "chunk_id": cid,
                    "document_id": row.Chunk.document_id,
                    "page": row.Chunk.page,
                    "content": row.Chunk.content,
                },
            )
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k_rrf + rank)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
    return [
        RetrievedChunk(
            chunk_id=cid,
            document_id=sources[cid]["document_id"],
            page=sources[cid].get("page"),
            content=sources[cid]["content"],
            score=score,
        )
        for cid, score in ranked
    ]
