"""Tests for dedup scoring."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from my_family_tree.core.ids import new_id
from my_family_tree.models.enums import PersonStatus, Sex
from my_family_tree.models.person import Person
from my_family_tree.resolve.dedup import score_candidates


def _person(
    *,
    given: str,
    surname: str,
    sex: Sex = Sex.male,
    birth_min: date | None = None,
    birth_max: date | None = None,
) -> Person:
    return Person(
        id=new_id(),
        tree_id=uuid4(),
        display_name=f"{given} {surname}",
        given_names=given,
        surname=surname,
        sex=sex,
        birth_min=birth_min,
        birth_max=birth_max,
        status=PersonStatus.active,
        confidence=100,
    )


@pytest.mark.unit
def test_identical_names_score_high() -> None:
    cand = _person(given="John", surname="Smith")
    scores = score_candidates(
        target_given="John",
        target_surname="Smith",
        target_birth=(None, None),
        target_sex=Sex.male,
        candidates=[cand],
    )
    assert scores[0].score > 0.6


@pytest.mark.unit
def test_different_names_score_low() -> None:
    cand = _person(given="Mary", surname="Johnson")
    scores = score_candidates(
        target_given="John",
        target_surname="Smith",
        target_birth=(None, None),
        target_sex=Sex.male,
        candidates=[cand],
    )
    assert scores[0].score < 0.6


@pytest.mark.unit
def test_overlapping_birth_dates_boost_score() -> None:
    near_match = _person(
        given="John",
        surname="Smith",
        birth_min=date(1842, 1, 1),
        birth_max=date(1842, 12, 31),
    )
    scores = score_candidates(
        target_given="John",
        target_surname="Smith",
        target_birth=(date(1842, 6, 1), date(1842, 8, 31)),
        target_sex=Sex.male,
        candidates=[near_match],
    )
    # The date overlap component is non-zero so the total should exceed 0.6.
    assert scores[0].score > 0.7
    assert scores[0].components["dates"] > 0
