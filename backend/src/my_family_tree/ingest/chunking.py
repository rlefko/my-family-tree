"""Sentence-boundary-aware chunker. Targets 800 tokens with 100-token overlap.

Token counter uses tiktoken's o200k_base encoding (close enough for sizing
decisions even when the embedding model is different)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pysbd
import tiktoken

_ENCODER = tiktoken.get_encoding("o200k_base")


@dataclass(slots=True)
class TextChunk:
    seq: int
    content: str
    start_char: int
    end_char: int
    tokens: int
    page: int | None = None


def count_tokens(text: str) -> int:
    return len(_ENCODER.encode(text))


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
    if not text.strip():
        return []
    segmenter = pysbd.Segmenter(language=language, clean=False, char_span=True)
    sentences = segmenter.segment(text)

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
        s_text = getattr(s, "sent", str(s))
        s_start = getattr(s, "start", buf_end)
        s_end = getattr(s, "end", s_start + len(s_text))
        s_tokens = count_tokens(s_text)
        if buf_text and buf_tokens + s_tokens > target_tokens:
            emit()
            # carry overlap from the tail of the previous buffer
            tail = _take_tail(buf_text, overlap_tokens)
            buf_text = list(tail)
            buf_start = max(s_start - sum(len(t) for t in tail), 0)
            buf_end = s_start
            buf_tokens = sum(count_tokens(t) for t in buf_text)
        if not buf_text:
            buf_start = s_start
        buf_text.append(s_text)
        buf_end = s_end
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
