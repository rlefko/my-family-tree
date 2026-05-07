"""Tests for stable conflict IDs."""

from __future__ import annotations

from uuid import uuid4

import pytest

from my_family_tree.models.enums import ConflictKind
from my_family_tree.resolve.conflicts import stable_conflict_id


@pytest.mark.unit
def test_same_inputs_yield_same_id() -> None:
    sid = uuid4()
    a = stable_conflict_id(
        kind=ConflictKind.date_mismatch, subject_ids=[sid], predicate="birth_date"
    )
    b = stable_conflict_id(
        kind=ConflictKind.date_mismatch, subject_ids=[sid], predicate="birth_date"
    )
    assert a == b


@pytest.mark.unit
def test_subject_id_order_does_not_affect_id() -> None:
    sid_a, sid_b = uuid4(), uuid4()
    one = stable_conflict_id(kind=ConflictKind.duplicate_person, subject_ids=[sid_a, sid_b])
    other = stable_conflict_id(kind=ConflictKind.duplicate_person, subject_ids=[sid_b, sid_a])
    assert one == other


@pytest.mark.unit
def test_different_kind_yields_different_id() -> None:
    sid = uuid4()
    a = stable_conflict_id(kind=ConflictKind.date_mismatch, subject_ids=[sid])
    b = stable_conflict_id(kind=ConflictKind.place_mismatch, subject_ids=[sid])
    assert a != b
