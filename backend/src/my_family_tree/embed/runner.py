"""Batched embedding runner. Reads chunks needing embeddings, calls the
provider in batches, writes both the full-precision `embedding` column and the
HNSW-indexable `embedding_half` column."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.core.logging import get_logger
from my_family_tree.embed.client import EmbeddingsClient
from my_family_tree.models.chunk import Chunk

log = get_logger(__name__)


async def embed_chunks_in_batches(
    session: AsyncSession,
    *,
    client: EmbeddingsClient,
    document_id: UUID | None = None,
    batch_size: int = 100,
) -> int:
    """Embed every chunk that has no `embedding` yet. Returns the count
    embedded. Caller is responsible for the transaction boundary."""
    stmt = select(Chunk).where(Chunk.embedding.is_(None))
    if document_id is not None:
        stmt = stmt.where(Chunk.document_id == document_id)
    chunks = list((await session.execute(stmt)).scalars().all())
    total = 0
    for batch in _batched(chunks, batch_size):
        texts = [c.content for c in batch]
        vectors = await client.embed(texts)
        for chunk, vector in zip(batch, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_half = vector
        total += len(batch)
        log.info("embed.batch", count=len(batch), total=total)
    return total


def _batched(items: list[Chunk], n: int) -> Iterable[list[Chunk]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]
