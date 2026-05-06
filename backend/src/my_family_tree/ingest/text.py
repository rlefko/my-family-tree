"""Plain-text extractor. UTF-8 with chardet fallback."""

from __future__ import annotations

import chardet


def extract_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        guess = chardet.detect(data)
        encoding = guess.get("encoding") or "latin-1"
        return data.decode(encoding, errors="replace")
