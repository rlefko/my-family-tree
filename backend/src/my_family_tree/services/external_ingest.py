"""External-content ingestion service.

Fetches a URL via the SSRF-guarded HTTP layer, normalizes the body to plain
text, and persists it as a `Document(kind=web)` plus a paired
`Source(kind=web)`. The same ingest pipeline that handles user uploads
then chunks and embeds the text so it becomes vector-searchable.

Idempotency is keyed on `(tree_id, sha256(cleaned_text))`. Different URLs
that resolve to byte-identical bodies collapse into one `Document`; a URL
whose body changes between calls produces a new `Document` row and leaves
the previous revision intact for audit."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.db.session import session_scope
from my_family_tree.embed.client import EmbeddingsClient
from my_family_tree.external.fetch import fetch_url
from my_family_tree.ingest.lifecycle import count_chunks, has_embedding
from my_family_tree.ingest.pipeline import PipelineDeps, run_pipeline
from my_family_tree.models.document import Document
from my_family_tree.models.enums import DocumentKind, ProcessingStatus, SourceKind
from my_family_tree.models.source import Source
from my_family_tree.storage.s3 import ObjectStore, storage_key

log = get_logger(__name__)


# `Document.original_filename` is `max_length=500`. URLs (or page titles)
# can exceed that; we truncate before insert.
_FILENAME_MAX = 500


@dataclass(slots=True, frozen=True)
class ExternalIngestResult:
    document_id: UUID
    source_id: UUID
    chunk_count: int
    embedded: bool
    dedup_hit: bool


@dataclass(slots=True)
class ExternalIngestService:
    """Wraps `ingest_web_url` so the chat router and MCP tool can share one
    object that owns the long-lived storage handle and embeddings client."""

    session_factory: async_sessionmaker[AsyncSession]
    storage: ObjectStore
    embeddings: EmbeddingsClient | None
    http: httpx.AsyncClient | None = None

    async def ingest(
        self, *, tree_id: UUID, url: str, title: str | None = None
    ) -> ExternalIngestResult:
        page = await fetch_url(url, client=self.http)
        body = page.text.encode("utf-8")
        async with session_scope(self.session_factory) as session:
            existing = await _find_existing(session, tree_id=tree_id, sha256=page.sha256)
            if existing is not None:
                source_id = await _find_or_create_source_for_document(
                    session,
                    tree_id=tree_id,
                    document_id=existing.id,
                    url=page.url,
                    title=title or page.title,
                )
                chunk_count = await count_chunks(session, existing.id)
                embedded = await has_embedding(session, existing.id)
                return ExternalIngestResult(
                    document_id=existing.id,
                    source_id=source_id,
                    chunk_count=chunk_count,
                    embedded=embedded,
                    dedup_hit=True,
                )
            key = storage_key(str(tree_id), page.sha256, "txt")
            stored = await self.storage.put(key, body, content_type="text/plain")
            document = Document(
                tree_id=tree_id,
                kind=DocumentKind.web,
                original_filename=_filename_for(url, title or page.title),
                mime_type="text/plain",
                byte_size=stored.size,
                sha256=page.sha256,
                storage_key=key,
                storage_bucket=stored.bucket,
                status=ProcessingStatus.pending,
                pages=None,
                language=None,
                ocr_engine=None,
                error=None,
                attempts=0,
                meta_json={
                    "web_url": page.url,
                    "fetched_at": page.fetched_at.isoformat(),
                    "fetched_title": page.title,
                    "content_type": page.content_type,
                },
            )
            session.add(document)
            await session.flush()
            source = Source(
                tree_id=tree_id,
                kind=SourceKind.other,  # SourceKind has no `web`; we tag origin in meta_json.
                title=(title or page.title or _hostname(page.url) or "web page")[:_FILENAME_MAX],
                url=page.url,
                accessed_at=utcnow(),
                document_id=document.id,
                meta_json={"origin": "web", "sha256": page.sha256},
            )
            session.add(source)
            await session.flush()
            document_id = document.id
            source_id = source.id
        # Run the pipeline outside the prior transaction so its per-step
        # commits land cleanly. The pipeline opens its own sessions via the
        # session_factory.
        await run_pipeline(
            self.session_factory,
            document_id=document_id,
            storage=self.storage,
            deps=PipelineDeps(embeddings=self.embeddings),
        )
        async with session_scope(self.session_factory) as session:
            chunk_count = await count_chunks(session, document_id)
            embedded = self.embeddings is not None and await has_embedding(session, document_id)
        return ExternalIngestResult(
            document_id=document_id,
            source_id=source_id,
            chunk_count=chunk_count,
            embedded=embedded,
            dedup_hit=False,
        )


async def _find_existing(session: AsyncSession, *, tree_id: UUID, sha256: str) -> Document | None:
    stmt = (
        select(Document)
        .where(Document.tree_id == tree_id)
        .where(Document.sha256 == sha256)
        .where(Document.kind == DocumentKind.web)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _find_or_create_source_for_document(
    session: AsyncSession,
    *,
    tree_id: UUID,
    document_id: UUID,
    url: str,
    title: str | None,
) -> UUID:
    stmt = (
        select(Source)
        .where(Source.tree_id == tree_id)
        .where(Source.document_id == document_id)
        .where(Source.url == url)
        .limit(1)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing.id
    source = Source(
        tree_id=tree_id,
        kind=SourceKind.other,
        title=(title or _hostname(url) or "web page")[:_FILENAME_MAX],
        url=url,
        accessed_at=utcnow(),
        document_id=document_id,
        meta_json={"origin": "web"},
    )
    session.add(source)
    await session.flush()
    return source.id


def _filename_for(url: str, title: str | None) -> str:
    """Pick a human-readable `original_filename` for a web Document.

    Prefer the `<title>` when present, then the URL host, capped at the
    column's `max_length`. Pure URLs can exceed 500 chars in pathological
    query strings; we always truncate."""
    candidate = title or _hostname(url) or url
    return candidate[:_FILENAME_MAX]


def _hostname(url: str) -> str | None:
    parsed = urlparse(url)
    return parsed.hostname


def build_external_ingest_service(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: ObjectStore,
    embeddings: EmbeddingsClient | None,
    http: httpx.AsyncClient | None = None,
) -> ExternalIngestService:
    return ExternalIngestService(
        session_factory=session_factory,
        storage=storage,
        embeddings=embeddings,
        http=http,
    )


__all__ = [
    "ExternalIngestResult",
    "ExternalIngestService",
    "build_external_ingest_service",
]
