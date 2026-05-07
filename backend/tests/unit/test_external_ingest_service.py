"""Smoke tests for `services/external_ingest.py`.

The service orchestrates fetch -> storage put -> Document insert ->
pipeline. A genuine end-to-end happy-path test requires Postgres + MinIO
(see `tests/integration/`). This unit suite focuses on the shape of the
service: what it imports, what `build_external_ingest_service` returns,
and the file-name truncation helper that's pure logic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from my_family_tree.services.external_ingest import (
    ExternalIngestService,
    _filename_for,
    build_external_ingest_service,
)


@pytest.mark.unit
def test_build_returns_service_instance() -> None:
    service = build_external_ingest_service(
        session_factory=MagicMock(),
        storage=MagicMock(),
        embeddings=None,
    )
    assert isinstance(service, ExternalIngestService)
    assert service.embeddings is None


@pytest.mark.unit
def test_filename_uses_title_when_present() -> None:
    assert _filename_for("https://example.com/x", "Jane Doe Obituary") == "Jane Doe Obituary"


@pytest.mark.unit
def test_filename_falls_back_to_host() -> None:
    assert _filename_for("https://example.com/page?q=v", None) == "example.com"


@pytest.mark.unit
def test_filename_truncated_at_500_chars() -> None:
    long_title = "x" * 1000
    out = _filename_for("https://example.com/", long_title)
    assert len(out) == 500


@pytest.mark.unit
def test_filename_falls_back_to_url_when_no_host() -> None:
    out = _filename_for("not-a-url", None)
    # urlparse on a relative-looking string returns an empty hostname; we
    # fall through to the url itself.
    assert out == "not-a-url"
