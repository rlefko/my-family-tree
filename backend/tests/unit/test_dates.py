"""Tests for the genealogical date parser."""

from __future__ import annotations

from datetime import date

import pytest

from my_family_tree.core.dates import DatePrecision, DateRange


@pytest.mark.unit
def test_iso_day() -> None:
    r = DateRange.from_text("1842-03-12")
    assert r.date_min == date(1842, 3, 12)
    assert r.date_max == date(1842, 3, 12)
    assert r.precision == DatePrecision.DAY


@pytest.mark.unit
def test_iso_month_expands_to_full_month() -> None:
    r = DateRange.from_text("1842-02")
    assert r.date_min == date(1842, 2, 1)
    assert r.date_max == date(1842, 2, 28)
    assert r.precision == DatePrecision.MONTH


@pytest.mark.unit
def test_bare_year() -> None:
    r = DateRange.from_text("1842")
    assert r.date_min == date(1842, 1, 1)
    assert r.date_max == date(1842, 12, 31)
    assert r.precision == DatePrecision.YEAR


@pytest.mark.unit
def test_circa_prefix_marks_circa() -> None:
    r = DateRange.from_text("abt. 1842")
    assert r.circa is True
    assert r.date_min == date(1842, 1, 1)


@pytest.mark.unit
def test_decade() -> None:
    r = DateRange.from_text("1840s")
    assert r.date_min == date(1840, 1, 1)
    assert r.date_max == date(1849, 12, 31)
    assert r.precision == DatePrecision.DECADE


@pytest.mark.unit
def test_century() -> None:
    r = DateRange.from_text("19th century")
    assert r.date_min == date(1801, 1, 1)
    assert r.date_max == date(1900, 12, 31)
    assert r.precision == DatePrecision.CENTURY


@pytest.mark.unit
def test_before() -> None:
    r = DateRange.from_text("before 1842")
    assert r.date_max == date(1842, 1, 1)


@pytest.mark.unit
def test_after() -> None:
    r = DateRange.from_text("after 1842")
    assert r.date_min == date(1842, 12, 31)


@pytest.mark.unit
def test_unknown_text_round_trips() -> None:
    r = DateRange.from_text("some weekday in late spring")
    assert r.text == "some weekday in late spring"
    assert r.date_min is None
    assert r.date_max is None
    assert r.precision == DatePrecision.UNKNOWN
