"""Tests for the sentence-aware chunker."""

from __future__ import annotations

import pytest

from my_family_tree.ingest.chunking import chunk_text, count_tokens


@pytest.mark.unit
def test_empty_text_returns_no_chunks() -> None:
    assert chunk_text("") == []


@pytest.mark.unit
def test_short_text_one_chunk() -> None:
    chunks = chunk_text("Hello world. This is a short passage.")
    assert len(chunks) == 1
    assert chunks[0].seq == 0
    assert "Hello world" in chunks[0].content


@pytest.mark.unit
def test_token_counter_basic() -> None:
    assert count_tokens("hello") > 0
    assert count_tokens("hello world") >= count_tokens("hello")


@pytest.mark.unit
def test_long_text_splits_into_multiple_chunks() -> None:
    sentence = "John Doe was born in 1842 in Boston, Massachusetts. "
    text = sentence * 200
    chunks = chunk_text(text, target_tokens=200, overlap_tokens=20)
    assert len(chunks) > 1
    # Each chunk's recorded token count is within range.
    for c in chunks:
        assert c.tokens <= 400  # generous upper bound including overlap effects
