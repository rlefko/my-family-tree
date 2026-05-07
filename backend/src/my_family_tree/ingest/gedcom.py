"""GEDCOM importer. Uses `python-gedcom` to parse INDI/FAM records. Each
record becomes a chunk (for search) and emits high-confidence claims with
`extractor='gedcom'`."""

from __future__ import annotations

import io
from dataclasses import dataclass

_TAG_INDEX = 2  # `0 @XREF@ TAG` → tag is the 3rd whitespace-separated token


@dataclass(slots=True)
class GedcomRecord:
    xref: str
    tag: str
    rendered: str
    raw: str


def parse(data: bytes) -> list[GedcomRecord]:
    """Parse a GEDCOM blob into a flat list of INDI and FAM records.

    The full python-gedcom API is heavyweight; for v1 we just split on the
    top-level `0 @XREF@ TAG` lines and return chunks suitable for the search
    index. Detailed claim extraction is a v2 step.
    """
    text = data.decode("utf-8", errors="replace")
    records: list[GedcomRecord] = []
    current_lines: list[str] = []
    current_xref = ""
    current_tag = ""
    buf = io.StringIO()

    def flush() -> None:
        if current_xref and current_tag in {"INDI", "FAM"}:
            raw = "\n".join(current_lines)
            records.append(
                GedcomRecord(
                    xref=current_xref,
                    tag=current_tag,
                    rendered=_render(current_lines),
                    raw=raw,
                )
            )
        current_lines.clear()
        buf.truncate(0)

    for line in text.splitlines():
        if line.startswith("0 ") and " @" in line and "@ " in line[2:]:
            flush()
            parts = line.split()
            current_xref = parts[1]
            current_tag = parts[_TAG_INDEX] if len(parts) > _TAG_INDEX else ""
            current_lines.append(line)
        else:
            current_lines.append(line)
    flush()
    return records


def _render(lines: list[str]) -> str:
    """Render a GEDCOM record as readable text, stripping level numbers."""
    rendered: list[str] = []
    for line in lines:
        parts = line.split(" ", 1)
        if not parts:
            continue
        tail = parts[1] if len(parts) > 1 else ""
        rendered.append(tail.strip())
    return "\n".join(rendered).strip()
