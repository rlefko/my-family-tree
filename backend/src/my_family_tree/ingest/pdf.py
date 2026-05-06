"""PDF text-layer extractor using pypdfium2. For scanned PDFs (no text layer),
the OCR path takes over (`ingest/image.py`)."""

from __future__ import annotations

from dataclasses import dataclass

import pypdfium2 as pdfium


@dataclass(slots=True)
class PdfPage:
    page: int
    text: str


def extract_pages(data: bytes) -> list[PdfPage]:
    """Extract per-page text from a PDF. Returns empty list of pages with empty
    text if the document has no extractable text layer; the caller decides
    whether to fall back to OCR."""
    pdf = pdfium.PdfDocument(data)
    pages: list[PdfPage] = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                tp = page.get_textpage()
                try:
                    text = tp.get_text_range() or ""
                finally:
                    tp.close()
            finally:
                page.close()
            pages.append(PdfPage(page=i + 1, text=text))
    finally:
        pdf.close()
    return pages


def has_text_layer(data: bytes, *, min_chars_per_page: int = 50) -> bool:
    pages = extract_pages(data)
    if not pages:
        return False
    avg = sum(len(p.text.strip()) for p in pages) / len(pages)
    return avg >= min_chars_per_page
