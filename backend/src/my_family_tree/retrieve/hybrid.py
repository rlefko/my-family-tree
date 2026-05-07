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
    document_filename: str | None = None
    document_kind: str | None = None


async def hybrid_search(
    session: AsyncSession,
    *,
    tree_id: UUID,
    query: str,
    embedding: list[float] | None = None,
    k: int = 10,
    k_rrf: int = 60,
    document_id: UUID | None = None,
) -> list[RetrievedChunk]:
    """Run an RRF-fused hybrid search. Caller provides an embedding; this
    function does not call the embeddings client itself, so it can be used
    in cost-sensitive or offline contexts. When `document_id` is set, results
    are scoped to a single document."""
    # The optional filter clause is two static strings, not user input; bind
    # parameters carry the values. Suppress the SQL-injection lint accordingly.
    doc_filter_sql = " AND chunk.document_id = :doc_id" if document_id is not None else ""
    fts_sql = (
        "SELECT chunk.id AS chunk_id, chunk.document_id, chunk.page, chunk.content, "  # noqa: S608
        "ts_rank_cd(chunk.tsv, plainto_tsquery('english', :q)) AS rank "
        "FROM chunk JOIN document ON document.id = chunk.document_id "
        "WHERE document.tree_id = :tree_id "
        "AND chunk.tsv @@ plainto_tsquery('english', :q)"
        f"{doc_filter_sql} "
        "ORDER BY rank DESC LIMIT :k3"
    )
    fts_stmt = text(fts_sql)
    fts_params: dict[str, object] = {"q": query, "tree_id": tree_id, "k3": k * 3}
    if document_id is not None:
        fts_params["doc_id"] = document_id
    fts_rows = (await session.execute(fts_stmt, fts_params)).mappings().all()

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
        if document_id is not None:
            vec_stmt = vec_stmt.where(Chunk.document_id == document_id)
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
    if not ranked:
        return []

    doc_ids = {sources[cid]["document_id"] for cid, _ in ranked}
    doc_meta = await _hydrate_document_meta(session, doc_ids)
    return [
        RetrievedChunk(
            chunk_id=cid,
            document_id=sources[cid]["document_id"],
            page=sources[cid].get("page"),
            content=sources[cid]["content"],
            score=score,
            document_filename=doc_meta.get(sources[cid]["document_id"], (None, None))[0],
            document_kind=doc_meta.get(sources[cid]["document_id"], (None, None))[1],
        )
        for cid, score in ranked
    ]


async def _hydrate_document_meta(
    session: AsyncSession, doc_ids: set[UUID]
) -> dict[UUID, tuple[str, str]]:
    """Map document_id -> (original_filename, kind) for citation rendering."""
    if not doc_ids:
        return {}
    stmt = select(Document.id, Document.original_filename, Document.kind).where(
        Document.id.in_(doc_ids)
    )
    rows = (await session.execute(stmt)).all()
    return {row[0]: (row[1], row[2].value) for row in rows}
