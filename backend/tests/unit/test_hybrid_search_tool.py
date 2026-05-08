"""Tests for the `hybrid_search` MCP tool's server-side embed path.

The agent passes a natural-language query without a precomputed embedding;
when `ToolContext.embeddings` is available, the tool must embed the query
itself and forward the vector to the shared `retrieve.hybrid_search` service.
Without an embeddings client, it must still work as FTS-only."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability
from my_family_tree.mcp.tools.chunks import HybridSearchInput, hybrid_search


@pytest.mark.unit
async def test_hybrid_search_embeds_query_when_no_embedding_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _retrieve(session: Any, **kwargs: Any) -> list[Any]:
        del session
        captured.update(kwargs)
        return []

    monkeypatch.setattr("my_family_tree.mcp.tools.chunks.retrieve_hybrid_search", _retrieve)
    # session_scope is an async context manager around session_factory; stub
    # the factory with a no-op so the tool's `async with` succeeds without a
    # real DB.
    factory = _SessionlessFactory()
    embeddings = MagicMock()
    embeddings.embed = AsyncMock(return_value=[[0.123] * 3072])
    ctx = ToolContext(
        session_factory=factory,
        tree_id=uuid4(),
        capabilities=Capability.READ,
        embeddings=embeddings,
    )

    out = await hybrid_search(ctx, HybridSearchInput(query="when was Jane born"))
    assert out.results == []
    embeddings.embed.assert_awaited_once_with(["when was Jane born"])
    assert captured["embedding"] == [0.123] * 3072
    assert captured["query"] == "when was Jane born"


@pytest.mark.unit
async def test_hybrid_search_falls_back_to_fts_only_without_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _retrieve(session: Any, **kwargs: Any) -> list[Any]:
        del session
        captured.update(kwargs)
        return []

    monkeypatch.setattr("my_family_tree.mcp.tools.chunks.retrieve_hybrid_search", _retrieve)
    factory = _SessionlessFactory()
    ctx = ToolContext(
        session_factory=factory,
        tree_id=uuid4(),
        capabilities=Capability.READ,
        embeddings=None,
    )

    await hybrid_search(ctx, HybridSearchInput(query="anything"))
    assert captured["embedding"] is None


@pytest.mark.unit
async def test_hybrid_search_uses_caller_embedding_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _retrieve(session: Any, **kwargs: Any) -> list[Any]:
        del session
        captured.update(kwargs)
        return []

    monkeypatch.setattr("my_family_tree.mcp.tools.chunks.retrieve_hybrid_search", _retrieve)
    factory = _SessionlessFactory()
    embeddings = MagicMock()
    embeddings.embed = AsyncMock()
    ctx = ToolContext(
        session_factory=factory,
        tree_id=uuid4(),
        capabilities=Capability.READ,
        embeddings=embeddings,
    )

    await hybrid_search(
        ctx,
        HybridSearchInput(query="precomputed", embedding=[0.5] * 3072),
    )
    embeddings.embed.assert_not_awaited()
    assert captured["embedding"] == [0.5] * 3072


class _SessionlessFactory:
    """Async sessionmaker stub that yields a no-op session.

    `hybrid_search` opens a session via `session_scope(ctx.session_factory)`
    but our stub `retrieve_hybrid_search` ignores it, so we just need to
    return an object with `commit`/`rollback` no-ops to satisfy the context
    manager."""

    def __call__(self) -> _SessionlessFactory:
        return self

    async def __aenter__(self) -> _SessionlessFactory:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None
