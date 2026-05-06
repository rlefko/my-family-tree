"""Sentence-boundary-aware chunker. Targets 800 tokens with 100-token overlap.

Token counter uses tiktoken's o200k_base encoding (close enough for sizing
decisions even when the embedding model is different).

Sentence segmentation uses a small inline regex splitter rather than `pysbd`;
pysbd ships invalid escape sequences that became hard `SyntaxError`s on
Python 3.14. The regex covers the common English cases (period / question
mark / exclamation point + whitespace + capital letter) plus typical
salutation abbreviations. Genealogy-specific quirks (e.g. "Wm.", "Jr.") are
fine: we err on the side of *not* splitting and the chunker is forgiving.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

import tiktoken

_ENCODER = tiktoken.get_encoding("o200k_base")


_ABBREV = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "st",
    "sr",
    "jr",
    "rev",
    "hon",
    "wm",
    "geo",
    "etc",
    "vs",
    "no",
    "fig",
    "abt",
    "ca",
    "circa",
    "approx",
    "co",
    "inc",
    "ltd",
}


@dataclass(slots=True)
class TextChunk:
    seq: int
    content: str
    start_char: int
    end_char: int
    tokens: int
    page: int | None = None


@dataclass(slots=True)
class _Sentence:
    text: str
    start: int
    end: int


def count_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


def _segment_sentences(text: str) -> list[_Sentence]:
    """Split text into sentences with character offsets. Boundaries are
    `[.!?]` (one or more) followed by whitespace and an uppercase letter,
    digit, or quote, with abbreviation guards."""
    if not text:
        return []
    sentences: list[_Sentence] = []
    cursor = 0
    pattern = re.compile(r"([.!?]+)(\s+)(?=[\"'(\[A-Z0-9])")
    for match in pattern.finditer(text):
        end = match.end(1)
        # Look back to see if the dot followed an abbreviation; if so, skip.
        prev_word = re.search(r"([A-Za-z]+)$", text[: end - len(match.group(1))])
        if prev_word and prev_word.group(1).lower() in _ABBREV:
            continue
        sent_text = text[cursor:end]
        if sent_text.strip():
            sentences.append(_Sentence(text=sent_text, start=cursor, end=end))
        cursor = match.end()
    if cursor < len(text):
        sent_text = text[cursor:]
        if sent_text.strip():
            sentences.append(_Sentence(text=sent_text, start=cursor, end=len(text)))
    return sentences


def chunk_text(
    text: str,
    *,
    page: int | None = None,
    target_tokens: int = 800,
    overlap_tokens: int = 100,
    language: str = "en",
) -> list[TextChunk]:
    """Split text into chunks of roughly `target_tokens` with `overlap_tokens`
    of overlap between consecutive chunks. Sentences are never split."""
    del language  # English only for v1; non-English deferred
    if not text.strip():
        return []
    sentences = _segment_sentences(text)

    chunks: list[TextChunk] = []
    buf_text: list[str] = []
    buf_start = 0
    buf_end = 0
    buf_tokens = 0
    seq = 0

    def emit() -> None:
        nonlocal seq, buf_text, buf_start, buf_end, buf_tokens
        if not buf_text:
            return
        content = "".join(buf_text)
        chunks.append(
            TextChunk(
                seq=seq,
                content=content,
                start_char=buf_start,
                end_char=buf_end,
                tokens=count_tokens(content),
                page=page,
            )
        )
        seq += 1

    for s in sentences:
        s_tokens = count_tokens(s.text)
        if buf_text and buf_tokens + s_tokens > target_tokens:
            emit()
            tail = list(_take_tail(buf_text, overlap_tokens))
            buf_text = tail
            buf_start = max(s.start - sum(len(t) for t in tail), 0)
            buf_end = s.start
            buf_tokens = sum(count_tokens(t) for t in buf_text)
        if not buf_text:
            buf_start = s.start
        buf_text.append(s.text)
        buf_end = s.end
        buf_tokens += s_tokens

    emit()
    return chunks


def _take_tail(parts: list[str], target_tokens: int) -> Iterator[str]:
    """Yield trailing parts whose combined token count is at least
    `target_tokens`, preserving order."""
    out: list[str] = []
    total = 0
    for part in reversed(parts):
        out.append(part)
        total += count_tokens(part)
        if total >= target_tokens:
            break
    yield from reversed(out)
