"""Shared pytest fixtures.

v1 ships unit tests only; integration tests against testcontainers Postgres /
Redis / MinIO are scaffolded under `tests/integration/` but require docker
and are gated behind the `integration` marker.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from my_family_tree.core.config import reset_settings_cache


@pytest.fixture(autouse=True)
def _isolate_env() -> Iterator[None]:
    """Snapshot env vars and restore them after each test so settings stay
    deterministic."""
    snapshot = dict(os.environ)
    reset_settings_cache()
    yield
    os.environ.clear()
    os.environ.update(snapshot)
    reset_settings_cache()
