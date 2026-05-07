"""Chunk retrieval: vector search and hybrid search (vector + FTS via RRF)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import RetrievedChunk
from my_family_tree.models.chunk import Chunk
from my_family_tree.models.document import Document

registry = get_registry()


class VectorSearchInput(BaseModel):
    embedding: list[float] = Field(min_length=3072, max_length=3072)
    k: int = Field(default=10, ge=1, le=100)
    document_id: UUID | None = None


class VectorSearchOutput(BaseModel):
    results: list[RetrievedChunk]


@registry.tool(
    name="vector_search",
    description=(
        "Vector similarity search over chunks using cosine distance on the "
        "halfvec embedding column. Pass a precomputed query embedding."
    ),
    input_model=VectorSearchInput,
    output_model=VectorSearchOutput,
    capability=Capability.READ,
)
async def vector_search(ctx: ToolContext, payload: VectorSearchInput) -> VectorSearchOutput:
    async with session_scope(ctx.session_factory) as session:
        # `<=>` is the cosine distance operator from pgvector.
        distance = Chunk.embedding_half.op("<=>")(payload.embedding).label("distance")
        stmt = (
            select(Chunk, distance)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.tree_id == ctx.tree_id)
        )
        if payload.document_id is not None:
            stmt = stmt.where(Chunk.document_id == payload.document_id)
        stmt = stmt.order_by(distance.asc()).limit(payload.k)
        rows = (await session.execute(stmt)).all()
        return VectorSearchOutput(
            results=[
                RetrievedChunk(
                    chunk_id=row.Chunk.id,
                    document_id=row.Chunk.document_id,
                    page=row.Chunk.page,
                    content=row.Chunk.content,
                    score=1.0 - float(row.distance),
                )
                for row in rows
            ]
        )


class HybridSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    embedding: list[float] | None = None
    k: int = Field(default=10, ge=1, le=100)
    k_rrf: int = Field(default=60, ge=1, le=1000)


class HybridSearchOutput(BaseModel):
    results: list[RetrievedChunk]


@registry.tool(
    name="hybrid_search",
    description=(
        "Hybrid search over chunks. Fuses vector similarity (if `embedding` "
        "provided) with Postgres FTS via Reciprocal Rank Fusion."
    ),
    input_model=HybridSearchInput,
    output_model=HybridSearchOutput,
    capability=Capability.READ,
)
async def hybrid_search(ctx: ToolContext, payload: HybridSearchInput) -> HybridSearchOutput:
    async with session_scope(ctx.session_factory) as session:
        # FTS rank: ts_rank_cd over the generated tsv column.
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
            (
                await session.execute(
                    fts_stmt,
                    {"q": payload.query, "tree_id": ctx.tree_id, "k3": payload.k * 3},
                )
            )
            .mappings()
            .all()
        )

        scores: dict[UUID, float] = {}
        sources: dict[UUID, dict] = {}
        for rank, row in enumerate(fts_rows, start=1):
            cid = row["chunk_id"]
            sources[cid] = dict(row)
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (payload.k_rrf + rank)

        if payload.embedding is not None:
            distance = Chunk.embedding_half.op("<=>")(payload.embedding).label("distance")
            vec_stmt = (
                select(Chunk, distance)
                .join(Document, Document.id == Chunk.document_id)
                .where(Document.tree_id == ctx.tree_id)
                .order_by(distance.asc())
                .limit(payload.k * 3)
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
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (payload.k_rrf + rank)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: payload.k]
        return HybridSearchOutput(
            results=[
                RetrievedChunk(
                    chunk_id=cid,
                    document_id=sources[cid]["document_id"],
                    page=sources[cid].get("page"),
                    content=sources[cid]["content"],
                    score=score,
                )
                for cid, score in ranked
            ]
        )


# Suppress unused-func warning.
_ = func
