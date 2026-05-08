"""Unit tests for the documents router. We mount the router on a fresh app
and override every dep so these stay fast and offline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from my_family_tree.api.deps import (
    EnqueueDep,
    SessionDep,
    SettingsDep,
    StorageDep,
    enqueue_pool_dep,
    session_dep,
    settings_dep,
    storage_dep,
)
from my_family_tree.api.errors import register_exception_handlers
from my_family_tree.api.routers.documents import router as documents_router
from my_family_tree.core.config import Settings
from my_family_tree.models.document import Document
from my_family_tree.models.enums import DocumentKind, ProcessingStatus

# Resolve dep aliases so type checkers see them as used.
_ = (EnqueueDep, SessionDep, SettingsDep, StorageDep)


def _build_app(
    *,
    found_doc: Document | None = None,
    pool: Any = None,
    storage: Any = None,
    settings: Settings | None = None,
) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(documents_router, prefix="/api/v1")

    session = MagicMock()
    # `await session.execute(...)` returns a result whose .scalar_one_or_none
    # returns `found_doc`. We don't tightly model the chained calls used by
    # other endpoints; tests only call upload here.
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=found_doc)
    exec_result.scalar_one = MagicMock(return_value=0)
    exec_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    session.execute = AsyncMock(return_value=exec_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()

    async def _session_dep() -> AsyncIterator[Any]:
        yield session

    app.dependency_overrides[session_dep] = _session_dep
    app.dependency_overrides[settings_dep] = lambda: settings or Settings()
    app.dependency_overrides[storage_dep] = lambda: storage or _fake_storage()
    app.dependency_overrides[enqueue_pool_dep] = lambda: pool or _fake_pool()

    return app


def _fake_storage() -> Any:
    storage = MagicMock()
    storage.bucket = "test-bucket"
    storage.put = AsyncMock()
    storage.delete = AsyncMock()
    return storage


def _fake_pool() -> Any:
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=MagicMock(job_id="job-1"))
    return pool


@pytest.mark.unit
def test_upload_rejects_oversize_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "16")
    app = _build_app()
    client = TestClient(app)
    payload = b"a" * 100
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("foo.txt", payload, "text/plain")},
        data={"tree_id": str(uuid4())},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "request_too_large"


@pytest.mark.unit
def test_upload_dedupe_returns_existing_without_enqueue() -> None:
    existing = Document(
        id=uuid4(),
        tree_id=uuid4(),
        kind=DocumentKind.text,
        original_filename="foo.txt",
        mime_type="text/plain",
        byte_size=4,
        sha256="x",
        storage_key="k",
        storage_bucket="b",
        status=ProcessingStatus.ready,
        meta_json={},
    )
    pool = _fake_pool()
    storage = _fake_storage()
    app = _build_app(found_doc=existing, pool=pool, storage=storage)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("foo.txt", b"abcd", "text/plain")},
        data={"tree_id": str(existing.tree_id)},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["document_id"] == str(existing.id)
    assert body["status"] == "ready"
    assert body["mime_type"] == "text/plain"
    assert body["original_filename"] == "foo.txt"
    pool.enqueue_job.assert_not_called()
    storage.put.assert_not_called()


@pytest.mark.unit
def test_upload_enqueues_ingest_job_once() -> None:
    pool = _fake_pool()
    storage = _fake_storage()
    app = _build_app(pool=pool, storage=storage)
    client = TestClient(app)
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("foo.txt", b"abcd", "text/plain")},
        data={"tree_id": str(uuid4())},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mime_type"] == "text/plain"
    assert body["original_filename"] == "foo.txt"
    pool.enqueue_job.assert_called_once()
    args, _ = pool.enqueue_job.call_args
    assert args[0] == "ingest_document"
    # Second arg is the SQLModel-defaulted UUID for the new Document.
    UUID(args[1])  # raises if not a UUID string
    storage.put.assert_called_once()


@pytest.mark.unit
def test_delete_calls_storage_delete() -> None:
    storage = _fake_storage()
    doc = Document(
        id=uuid4(),
        tree_id=uuid4(),
        kind=DocumentKind.text,
        original_filename="foo.txt",
        mime_type="text/plain",
        byte_size=4,
        sha256="x",
        storage_key="k",
        storage_bucket="b",
        status=ProcessingStatus.ready,
        meta_json={},
    )

    app = _build_app(storage=storage)
    # Override session.get to return our doc, and the source-count query to 0.
    sess_iter = app.dependency_overrides[session_dep]

    async def _override() -> AsyncIterator[Any]:
        async for s in sess_iter():
            s.get = AsyncMock(return_value=doc)
            yield s

    app.dependency_overrides[session_dep] = _override
    client = TestClient(app)
    resp = client.delete(f"/api/v1/documents/{doc.id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    storage.delete.assert_called_once_with(doc.storage_key)


@pytest.mark.unit
def test_reprocess_clears_processing_steps_and_enqueues() -> None:
    pool = _fake_pool()
    doc = Document(
        id=uuid4(),
        tree_id=uuid4(),
        kind=DocumentKind.text,
        original_filename="foo.txt",
        mime_type="text/plain",
        byte_size=4,
        sha256="x",
        storage_key="k",
        storage_bucket="b",
        status=ProcessingStatus.failed,
        meta_json={"processing_steps": ["extract_text", "chunk"], "vision_calls": [{"page": 1}]},
        error="kaboom",
        attempts=2,
    )

    app = _build_app(pool=pool)
    sess_iter = app.dependency_overrides[session_dep]

    async def _override() -> AsyncIterator[Any]:
        async for s in sess_iter():
            s.get = AsyncMock(return_value=doc)
            yield s

    app.dependency_overrides[session_dep] = _override
    client = TestClient(app)
    resp = client.post(f"/api/v1/documents/{doc.id}/reprocess")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert doc.meta_json["processing_steps"] == []
    assert "vision_calls" not in doc.meta_json
    assert doc.status == ProcessingStatus.pending
    assert doc.error is None
    assert doc.attempts == 0
    pool.enqueue_job.assert_called_once_with("ingest_document", str(doc.id))
