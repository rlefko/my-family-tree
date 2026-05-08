"""Chunk retrieval: vector search and hybrid search (vector + FTS via RRF).

The vector path stays inline; the hybrid path delegates to
`retrieve.hybrid.hybrid_search` so the REST endpoint and MCP tool share one
implementation."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from my_family_tree.db.session import session_scope
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import RetrievedChunk
from my_family_tree.models.chunk import Chunk
from my_family_tree.models.document import Document
from my_family_tree.retrieve.hybrid import hybrid_search as retrieve_hybrid_search

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
        # `cosine_distance` wraps `<=>` with `return_type=Float`, so the result
        # column does not get re-routed through HALFVEC's deserializer (which
        # would crash trying to subscript the scalar distance).
        distance = Chunk.embedding_half.cosine_distance(payload.embedding).label("distance")
        stmt = (
            select(Chunk, Document.original_filename, Document.kind, distance)
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
                    document_filename=row.original_filename,
                    document_kind=row.kind.value,
                )
                for row in rows
            ]
        )


class HybridSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    embedding: list[float] | None = None
    k: int = Field(default=10, ge=1, le=100)
    k_rrf: int = Field(default=60, ge=1, le=1000)
    document_id: UUID | None = None


class HybridSearchOutput(BaseModel):
    results: list[RetrievedChunk]


@registry.tool(
    name="hybrid_search",
    description=(
        "Hybrid search over chunks. Pass the user's natural-language `query`. "
        "When the host has an embeddings client configured, the query is "
        "embedded server-side and the results fuse vector similarity with "
        "Postgres FTS via Reciprocal Rank Fusion; otherwise this is FTS-only. "
        "Optionally scope to a single `document_id`. You usually do NOT need "
        "to compute or pass `embedding` yourself."
    ),
    input_model=HybridSearchInput,
    output_model=HybridSearchOutput,
    capability=Capability.READ,
)
async def hybrid_search(ctx: ToolContext, payload: HybridSearchInput) -> HybridSearchOutput:
    embedding = payload.embedding
    if embedding is None and ctx.embeddings is not None:
        # Embed the query server-side so the agent gets vector recall without
        # having to compute a 3072-dim vector itself. Falls back to FTS-only
        # when no embeddings client is configured.
        embedded = await ctx.embeddings.embed([payload.query])
        if embedded:
            embedding = embedded[0]
    async with session_scope(ctx.session_factory) as session:
        hits = await retrieve_hybrid_search(
            session,
            tree_id=ctx.tree_id,
            query=payload.query,
            embedding=embedding,
            k=payload.k,
            k_rrf=payload.k_rrf,
            document_id=payload.document_id,
        )
        return HybridSearchOutput(
            results=[
                RetrievedChunk(
                    chunk_id=h.chunk_id,
                    document_id=h.document_id,
                    page=h.page,
                    content=h.content,
                    score=h.score,
                    document_filename=h.document_filename,
                    document_kind=h.document_kind,
                )
                for h in hits
            ]
        )
