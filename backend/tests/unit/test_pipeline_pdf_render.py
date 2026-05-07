"""Unit tests for the PDF page rendering helper used by pdf_scan ingestion."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_family_tree.ingest.pdf import render_pages

FIXTURE = Path(__file__).parent.parent / "fixtures" / "two_page_blank.pdf"


@pytest.mark.unit
def test_render_pages_yields_one_per_page() -> None:
    data = FIXTURE.read_bytes()
    rendered = list(render_pages(data, scale=1.0))
    assert len(rendered) == 2
    nums = [page for page, _ in rendered]
    assert nums == [1, 2]


@pytest.mark.unit
def test_render_pages_returns_png_bytes() -> None:
    data = FIXTURE.read_bytes()
    rendered = list(render_pages(data, scale=1.0))
    for _page, png_bytes in rendered:
        # PNG magic bytes.
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(png_bytes) > 100
