"""Tests for UUIDv7 helpers."""

from __future__ import annotations

import time
from uuid import UUID

import pytest

from my_family_tree.core.ids import new_id, new_id_str


@pytest.mark.unit
def test_new_id_returns_uuid() -> None:
    assert isinstance(new_id(), UUID)


@pytest.mark.unit
def test_new_id_str_is_uuid_form() -> None:
    s = new_id_str()
    UUID(s)  # parses without error


@pytest.mark.unit
def test_uuid7_is_monotonic_within_a_second() -> None:
    a = new_id()
    time.sleep(0.001)
    b = new_id()
    assert a < b
