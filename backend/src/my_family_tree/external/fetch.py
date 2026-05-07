"""High-level URL -> cleaned-text fetcher used by the `web_fetch` MCP tool
and the `external_index_url` ingest service.

Wraps `external.http.fetch_text` (SSRF + size + content-type guarded) with
HTML-to-text extraction via `selectolax`. The output is suitable for both
LLM consumption and downstream chunking + embedding."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

import httpx
from selectolax.parser import HTMLParser

from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.external.http import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_S,
    DEFAULT_USER_AGENT,
    FetchResult,
    build_http_client,
    fetch_text,
)

log = get_logger(__name__)

# Tags whose contents should be removed entirely before extracting text.
# Keeping these in the output would either feed JavaScript / CSS to the LLM
# (token waste) or surface markup the user didn't actually read.
_STRIP_TAGS: tuple[str, ...] = (
    "script",
    "style",
    "noscript",
    "svg",
    "template",
    "iframe",
    "form",
    "header",
    "footer",
    "nav",
    "aside",
)


@dataclass(slots=True, frozen=True)
class FetchedPage:
    url: str
    title: str | None
    text: str
    fetched_at: datetime
    sha256: str
    byte_size: int
    content_type: str


async def fetch_url(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    user_agent: str = DEFAULT_USER_AGENT,
) -> FetchedPage:
    """Fetch a URL and return its cleaned plain text plus metadata.

    Pass an existing `client` to share a connection pool across calls;
    otherwise a short-lived one is built and torn down for this request."""
    own_client = client is None
    http = client or build_http_client(timeout_s=timeout_s, user_agent=user_agent)
    try:
        result = await fetch_text(http, url, max_bytes=max_bytes)
    finally:
        if own_client:
            await http.aclose()

    text, title = _extract_text_and_title(result)
    if not text.strip():
        raise ExternalProviderError(f"no extractable text at {url!r}")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return FetchedPage(
        url=result.url,
        title=title,
        text=text,
        fetched_at=utcnow(),
        sha256=sha,
        byte_size=result.byte_size,
        content_type=result.content_type,
    )


def _extract_text_and_title(result: FetchResult) -> tuple[str, str | None]:
    """Decode the response body and produce (cleaned_text, title).

    For HTML / XHTML we use selectolax to drop script-style-nav-etc. tags
    and concatenate the visible text. For plain text we just decode."""
    if result.content_type in {"text/html", "application/xhtml+xml"}:
        return _extract_html(result.body)
    text = result.body.decode("utf-8", errors="replace")
    return _normalize_whitespace(text), None


def _extract_html(body: bytes) -> tuple[str, str | None]:
    parser = HTMLParser(body)
    title_node = parser.css_first("title")
    title = title_node.text(strip=True) if title_node is not None else None
    parser.strip_tags(list(_STRIP_TAGS))
    if parser.body is None:
        return ("", title)
    raw = parser.body.text(separator=" ", strip=True)
    return _normalize_whitespace(raw), title


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to single spaces and trim. Keeps the
    output dense without losing word boundaries from selectolax's
    `separator=' '` join."""
    return " ".join(text.split())


__all__ = ["FetchedPage", "fetch_url"]
