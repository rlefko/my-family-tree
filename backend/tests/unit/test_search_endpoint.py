"""Unit tests for the /search/chunks endpoint. Stubs the embeddings client and
the shared hybrid_search service so the test stays offline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from my_family_tree.api.deps import (
    embeddings_client_dep,
    session_dep,
)
from my_family_tree.api.errors import register_exception_handlers
from my_family_tree.api.routers.search import router as search_router
from my_family_tree.core.errors import LLMProviderError
from my_family_tree.retrieve.hybrid import RetrievedChunk


@pytest.mark.unit
def test_search_chunks_returns_enriched_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(search_router, prefix="/api/v1")

    session = MagicMock()

    async def _session_dep() -> AsyncIterator[Any]:
        yield session

    fake_embeddings = MagicMock()
    fake_embeddings.embed = AsyncMock(return_value=[[0.0] * 3072])

    app.dependency_overrides[session_dep] = _session_dep
    app.dependency_overrides[embeddings_client_dep] = lambda: fake_embeddings

    chunk_id = uuid4()
    doc_id = uuid4()

    async def _hybrid_search(*args: Any, **kwargs: Any) -> list[RetrievedChunk]:
        del args, kwargs
        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=doc_id,
                page=2,
                content="An old census record",
                score=0.42,
                document_filename="census1900.pdf",
                document_kind="pdf_text",
            )
        ]

    monkeypatch.setattr("my_family_tree.api.routers.search.hybrid_search", _hybrid_search)

    client = TestClient(app)
    resp = client.post(
        "/api/v1/search/chunks",
        json={"tree_id": str(uuid4()), "query": "census 1900", "k": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["chunk_id"] == str(chunk_id)
    assert item["document_id"] == str(doc_id)
    assert item["document_filename"] == "census1900.pdf"
    assert item["document_kind"] == "pdf_text"
    assert item["page"] == 2
    assert item["score"] == pytest.approx(0.42)
    fake_embeddings.embed.assert_awaited_once_with(["census 1900"])


@pytest.mark.unit
def test_search_chunks_502_when_embeddings_unavailable() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(search_router, prefix="/api/v1")

    async def _session_dep() -> AsyncIterator[Any]:
        yield MagicMock()

    def _missing() -> Any:
        raise LLMProviderError("no key")

    app.dependency_overrides[session_dep] = _session_dep
    app.dependency_overrides[embeddings_client_dep] = _missing

    client = TestClient(app)
    resp = client.post(
        "/api/v1/search/chunks",
        json={"tree_id": str(uuid4()), "query": "x"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "llm_provider_error"
