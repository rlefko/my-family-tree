"""Unit tests for the in-memory vision spend ledger."""

from __future__ import annotations

from datetime import date

import pytest

from my_family_tree.llm.vision_ledger import VisionLedger


@pytest.mark.unit
def test_ledger_starts_under_cap() -> None:
    ledger = VisionLedger(cap_usd=1.0)
    assert ledger.under_cap(date(2026, 5, 7)) is True
    assert ledger.remaining_today(date(2026, 5, 7)) == pytest.approx(1.0)


@pytest.mark.unit
def test_record_accumulates_within_a_day() -> None:
    ledger = VisionLedger(cap_usd=1.0)
    today = date(2026, 5, 7)
    ledger.record(today, 0.4)
    ledger.record(today, 0.3)
    assert ledger.spend_today(today) == pytest.approx(0.7)
    assert ledger.remaining_today(today) == pytest.approx(0.3)


@pytest.mark.unit
def test_under_cap_flips_when_exhausted() -> None:
    ledger = VisionLedger(cap_usd=0.5)
    today = date(2026, 5, 7)
    ledger.record(today, 0.4)
    assert ledger.under_cap(today) is True
    ledger.record(today, 0.2)
    # 0.6 spent, cap 0.5, so under_cap is False.
    assert ledger.under_cap(today) is False


@pytest.mark.unit
def test_distinct_dates_do_not_collide() -> None:
    ledger = VisionLedger(cap_usd=1.0)
    monday = date(2026, 5, 4)
    tuesday = date(2026, 5, 5)
    ledger.record(monday, 0.9)
    assert ledger.under_cap(monday) is True
    assert ledger.under_cap(tuesday) is True
    ledger.record(tuesday, 0.1)
    assert ledger.spend_today(monday) == pytest.approx(0.9)
    assert ledger.spend_today(tuesday) == pytest.approx(0.1)
