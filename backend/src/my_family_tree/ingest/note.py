"""Free-form note extractor. Treats the input as text and tags the source kind
as `family_oral` so claims extracted from it get a confidence floor."""

from __future__ import annotations

from my_family_tree.ingest.text import extract_text


def extract_note(data: bytes) -> str:
    return extract_text(data)
