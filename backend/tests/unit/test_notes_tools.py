"""Schema and guard tests for the note MCP tools.

End-to-end note creation requires Postgres + MinIO for the ingest pipeline
(see `tests/integration/` once that lands). This unit suite focuses on the
shape of the tools, the registry wiring, and the early-return guards so
regressions in those surfaces are caught without containers."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from my_family_tree.core.errors import StorageError, ValidationError
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.tools.notes import (
    NoteCreateInput,
    NoteUpdateInput,
    note_create,
    note_update,
)


@pytest.mark.unit
def test_note_tools_are_registered_as_trivial_writes() -> None:
    registry = get_registry()
    for name in ("note_create", "note_update", "note_delete"):
        tool = registry.tools[name]
        assert tool.capability == Capability.TRIVIAL_WRITE
        assert tool.is_read_only is False


@pytest.mark.unit
def test_note_create_input_rejects_empty_body() -> None:
    with pytest.raises(PydanticValidationError):
        NoteCreateInput(title="t", body="")


@pytest.mark.unit
def test_note_create_input_rejects_oversize_body() -> None:
    body = "x" * 200_001
    with pytest.raises(PydanticValidationError):
        NoteCreateInput(title="t", body=body)


@pytest.mark.unit
async def test_note_update_requires_at_least_one_field() -> None:
    payload = NoteUpdateInput(document_id=uuid4())
    ctx = _ctx(storage=_DummyStorage(), embeddings=_DummyEmbeddings())
    with pytest.raises(ValidationError, match="at least one of title or body"):
        await note_update(ctx, payload)


@pytest.mark.unit
async def test_note_create_requires_storage() -> None:
    payload = NoteCreateInput(title="t", body="body")
    ctx = _ctx(storage=None, embeddings=_DummyEmbeddings())
    with pytest.raises(StorageError, match="storage backend"):
        await note_create(ctx, payload)


@pytest.mark.unit
async def test_note_create_requires_embeddings() -> None:
    payload = NoteCreateInput(title="t", body="body")
    ctx = _ctx(storage=_DummyStorage(), embeddings=None)
    with pytest.raises(StorageError, match="embeddings client"):
        await note_create(ctx, payload)


def _ctx(*, storage: Any, embeddings: Any) -> ToolContext:
    return ToolContext(
        session_factory=_NullSessionFactory(),  # type: ignore[arg-type]
        tree_id=uuid4(),
        capabilities=Capability.TRIVIAL_WRITE,
        storage=storage,
        embeddings=embeddings,
    )


class _NullSessionFactory:
    """Stand-in for `async_sessionmaker[AsyncSession]`. The guarded paths
    raise before the factory is ever called, so the methods are unimplemented
    and will fail loudly if a code path slips past the guards."""

    def __call__(self) -> Any:
        raise AssertionError("session factory should not be invoked under guard")


class _DummyStorage:
    bucket = "test"

    async def put(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("storage.put should not be invoked under guard")

    async def get(self, *args: Any, **kwargs: Any) -> bytes:
        raise AssertionError("storage.get should not be invoked under guard")

    async def delete(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("storage.delete should not be invoked under guard")


class _DummyEmbeddings:
    async def embed(self, *args: Any, **kwargs: Any) -> list[list[float]]:
        raise AssertionError("embeddings.embed should not be invoked under guard")
