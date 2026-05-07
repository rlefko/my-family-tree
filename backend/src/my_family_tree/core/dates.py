"""Genealogical date handling. Sources rarely give us a clean ISO date.

`DateRange` is a value object representing a fuzzy date with an inclusive
`[date_min, date_max]` interval, a verbatim text form, and a precision hint.
It is embedded inline on rows that need it (Person.birth_*, Event.date_*, etc.).
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import IntEnum

DECEMBER = 12
CIRCA_PREFIXES = ("abt.", "abt", "ca.", "ca", "circa", "c.", "around")


class DatePrecision(IntEnum):
    UNKNOWN = 0
    CENTURY = 1
    DECADE = 2
    YEAR = 3
    MONTH = 4
    DAY = 5


@dataclass(frozen=True, slots=True)
class DateRange:
    """A fuzzy date.

    Either `date_min`/`date_max` are both set (forming an inclusive interval)
    or both are `None` (unknown but possibly recorded as `text`).
    """

    text: str | None = None
    date_min: date | None = None
    date_max: date | None = None
    precision: DatePrecision = DatePrecision.UNKNOWN
    circa: bool = False

    @property
    def is_known(self) -> bool:
        return self.date_min is not None and self.date_max is not None

    @classmethod
    def from_year(cls, year: int, *, circa: bool = False) -> DateRange:
        return cls(
            text=f"abt. {year}" if circa else str(year),
            date_min=date(year, 1, 1),
            date_max=date(year, 12, 31),
            precision=DatePrecision.YEAR,
            circa=circa,
        )

    @classmethod
    def from_iso(cls, iso: str) -> DateRange:
        d = date.fromisoformat(iso)
        return cls(
            text=iso,
            date_min=d,
            date_max=d,
            precision=DatePrecision.DAY,
        )

    @classmethod
    def from_text(cls, text: str) -> DateRange:
        """Parse a small set of common genealogical date forms.

        v1 supports: ISO dates (`1842-03-12`), 4-digit years (`1842`), decade
        (`1840s`), century (`19th century`), `abt. / circa` prefixes,
        `before / after` prefixes, `between X and Y` ranges, and `X to Y`.
        Unrecognized strings round-trip the text with unknown precision.
        """
        original = text
        s = text.strip()
        if not s:
            return cls()

        circa, s = _strip_circa_prefix(s)
        for parser in _PARSERS:
            result = parser(s, original=original, circa=circa)
            if result is not None:
                return result
        return cls(text=original)


# Parser helpers split out so `from_text` stays a flat dispatch table and ruff's
# branch-count checks are happy.


def _strip_circa_prefix(s: str) -> tuple[bool, str]:
    lowered = s.lower()
    for prefix in CIRCA_PREFIXES:
        if lowered.startswith(prefix + " "):
            return True, s[len(prefix) + 1 :].strip()
    return False, s


def _parse_before(s: str, *, original: str, circa: bool) -> DateRange | None:
    del circa  # circa is meaningless on a strict upper bound
    m = re.match(r"^(?:before|bef\.?|<)\s+(.+)$", s, re.IGNORECASE)
    if not m:
        return None
    inner = DateRange.from_text(m.group(1))
    if inner.date_min is None:
        return None
    return DateRange(
        text=original,
        date_min=date(1, 1, 1),
        date_max=inner.date_min,
        precision=inner.precision,
        circa=False,
    )


def _parse_after(s: str, *, original: str, circa: bool) -> DateRange | None:
    del circa
    m = re.match(r"^(?:after|aft\.?|>)\s+(.+)$", s, re.IGNORECASE)
    if not m:
        return None
    inner = DateRange.from_text(m.group(1))
    if inner.date_max is None:
        return None
    return DateRange(
        text=original,
        date_min=inner.date_max,
        date_max=date(9999, 12, 31),
        precision=inner.precision,
        circa=False,
    )


def _parse_range(s: str, *, original: str, circa: bool) -> DateRange | None:
    m = re.match(r"^(?:between\s+)?(.+?)\s+(?:and|to|-)\s+(.+)$", s, re.IGNORECASE)
    if not m:
        return None
    left = DateRange.from_text(m.group(1))
    right = DateRange.from_text(m.group(2))
    if left.date_min is None or right.date_max is None:
        return None
    return DateRange(
        text=original,
        date_min=left.date_min,
        date_max=right.date_max,
        precision=DatePrecision(min(left.precision, right.precision)),
        circa=circa,
    )


def _parse_iso_day(s: str, *, original: str, circa: bool) -> DateRange | None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    d = date.fromisoformat(s)
    return DateRange(
        text=original,
        date_min=d,
        date_max=d,
        precision=DatePrecision.DAY,
        circa=circa,
    )


def _parse_iso_month(s: str, *, original: str, circa: bool) -> DateRange | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    return DateRange(
        text=original,
        date_min=date(year, month, 1),
        date_max=_last_day_of_month(year, month),
        precision=DatePrecision.MONTH,
        circa=circa,
    )


def _parse_decade(s: str, *, original: str, circa: bool) -> DateRange | None:
    m = re.fullmatch(r"(\d{3})0s", s)
    if not m:
        return None
    decade = int(m.group(1)) * 10
    return DateRange(
        text=original,
        date_min=date(decade, 1, 1),
        date_max=date(decade + 9, 12, 31),
        precision=DatePrecision.DECADE,
        circa=circa,
    )


def _parse_century(s: str, *, original: str, circa: bool) -> DateRange | None:
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)\s+century", s, re.IGNORECASE)
    if not m:
        return None
    century = int(m.group(1))
    start = (century - 1) * 100 + 1
    return DateRange(
        text=original,
        date_min=date(start, 1, 1),
        date_max=date(start + 99, 12, 31),
        precision=DatePrecision.CENTURY,
        circa=circa,
    )


def _parse_year(s: str, *, original: str, circa: bool) -> DateRange | None:
    if not re.fullmatch(r"\d{4}", s):
        return None
    year = int(s)
    out = DateRange.from_year(year, circa=circa)
    return DateRange(
        text=original,
        date_min=out.date_min,
        date_max=out.date_max,
        precision=out.precision,
        circa=out.circa,
    )


_Parser = Callable[..., "DateRange | None"]
_PARSERS: tuple[_Parser, ...] = (
    _parse_before,
    _parse_after,
    _parse_range,
    _parse_iso_day,
    _parse_iso_month,
    _parse_decade,
    _parse_century,
    _parse_year,
)


def _last_day_of_month(year: int, month: int) -> date:
    if month == DECEMBER:
        return date(year, 12, 31)
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day)
