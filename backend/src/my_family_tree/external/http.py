"""Shared HTTP utilities for external services.

Two guarantees this module enforces uniformly so callers never re-implement
them:

1. **SSRF protection.** Every outbound URL is validated before the first
   socket call and again after every redirect. We refuse non-`http`/`https`
   schemes, refuse hostnames that resolve to private, loopback, link-local,
   multicast, or otherwise reserved IPv4 / IPv6 ranges, and refuse literal
   IP addresses in those ranges. The list of blocked ranges is intentionally
   broad: cloud-instance metadata services, RFC1918 networks, IPv6 ULA, and
   IPv4-mapped IPv6 of any of the above.

2. **Response-size and content-type caps.** `fetch_text` streams the body
   and aborts as soon as the cumulative byte count exceeds `max_bytes`, and
   it refuses content types outside the allowlist. This keeps a malicious
   URL from OOM-ing the api container or feeding non-text payloads to the
   LLM.

Redirects are followed manually with a hop limit because httpx's built-in
follower would skip our `validate_url` check on each hop."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx

from my_family_tree.core.errors import ExternalProviderError, UnsafeUrlError
from my_family_tree.core.logging import get_logger

log = get_logger(__name__)


DEFAULT_USER_AGENT = "my-family-tree/0.1 (+https://github.com/rlefkowitz/my-family-tree)"

# Content types accepted by `fetch_text`. We don't ingest binary types here;
# pdf/image flow through the upload + OCR pipeline.
DEFAULT_TEXT_CONTENT_TYPES: frozenset[str] = frozenset(
    {"text/html", "text/plain", "application/xhtml+xml", "application/xml"}
)

DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_TIMEOUT_S = 20.0
DEFAULT_MAX_REDIRECTS = 5


def build_http_client(
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    user_agent: str = DEFAULT_USER_AGENT,
    extra_headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Construct a shared `httpx.AsyncClient` for external calls.

    Manual redirect handling is enforced by `follow_redirects=False`.
    Callers that need to follow redirects must use `fetch_text` (or
    `_iter_redirects` for custom flows), which re-runs `validate_url` on
    every hop."""
    headers = {"User-Agent": user_agent, "Accept-Encoding": "identity"}
    if extra_headers:
        headers.update(extra_headers)
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s),
        follow_redirects=False,
        headers=headers,
    )


def validate_url(url: str) -> None:
    """Reject obviously unsafe URLs before any network call.

    Raises `UnsafeUrlError` for: non-http(s) schemes, missing hosts, hosts
    that resolve to private/loopback/link-local/multicast/reserved
    addresses, and literal IPs in any of those ranges.

    DNS resolution happens here so a redirect target can be re-validated
    end-to-end. Hosts that fail to resolve are rejected too: the caller
    can't safely call something we can't even resolve."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError(f"refusing url with scheme {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("url has no host component")
    addresses = _resolve_all(host)
    if not addresses:
        raise UnsafeUrlError(f"unable to resolve host {host!r}")
    for ip in addresses:
        if _is_blocked_ip(ip):
            raise UnsafeUrlError(f"host {host!r} resolves to blocked address {ip}")


def _resolve_all(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a host to every A / AAAA record. Literal IPs short-circuit
    the lookup. Returns an empty list on resolution failure so the caller
    rejects the URL rather than racing the DNS resolver."""
    try:
        addr = ipaddress.ip_address(host)
        return [addr]
    except ValueError:
        pass
    try:
        records = socket.getaddrinfo(host, None)
    except OSError:
        return []
    out: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for record in records:
        sockaddr = record[4]
        raw = sockaddr[0]
        if not isinstance(raw, str):
            continue
        if raw in seen:
            continue
        seen.add(raw)
        try:
            out.append(ipaddress.ip_address(raw))
        except ValueError:
            continue
    return out


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True for IPs we never want to send a request to."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    ):
        return True
    # IPv6-mapped IPv4 (::ffff:a.b.c.d) needs a separate check because the
    # IPv6 properties above don't always look at the embedded IPv4 address.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_blocked_ip(ip.ipv4_mapped)
    return False


@asynccontextmanager
async def open_http_client(
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    user_agent: str = DEFAULT_USER_AGENT,
    extra_headers: dict[str, str] | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a short-lived `httpx.AsyncClient`. Use this when a tool call
    only needs one or two requests; long-lived clients should be built via
    `build_http_client` and kept on the service object."""
    client = build_http_client(
        timeout_s=timeout_s, user_agent=user_agent, extra_headers=extra_headers
    )
    try:
        yield client
    finally:
        await client.aclose()


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed_content_types: Iterable[str] = DEFAULT_TEXT_CONTENT_TYPES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> FetchResult:
    """Fetch a URL as text under SSRF, size, and content-type guards.

    Streams the response and aborts the read as soon as `max_bytes` is
    exceeded. Re-validates every redirect target through `validate_url`.

    Returns a `FetchResult(url, status, content_type, body, byte_size)`
    where `url` is the *final* URL after redirects."""
    allowed = {ct.lower() for ct in allowed_content_types}
    current = url
    for hop in range(max_redirects + 1):
        validate_url(current)
        async with client.stream("GET", current) as response:
            if response.is_redirect:
                if hop == max_redirects:
                    raise ExternalProviderError(
                        f"too many redirects fetching {url!r} (limit {max_redirects})"
                    )
                location = response.headers.get("location")
                if not location:
                    raise ExternalProviderError(f"redirect with no Location header at {current!r}")
                current = str(httpx.URL(current).join(location))
                # Drain any body so the connection can be reused, but
                # don't read into memory; the next loop iteration opens a
                # fresh stream after re-validating the target.
                continue
            response.raise_for_status()
            content_type = (
                (response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            )
            if content_type not in allowed:
                raise ExternalProviderError(
                    f"refusing content type {content_type!r} (allowed: {sorted(allowed)})"
                )
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ExternalProviderError(
                        f"response exceeded {max_bytes} bytes (so far {total})"
                    )
                chunks.append(chunk)
            body = b"".join(chunks)
            return FetchResult(
                url=str(response.url),
                status=response.status_code,
                content_type=content_type,
                body=body,
                byte_size=total,
            )
    # Unreachable: the loop either returns, raises, or keeps redirecting
    # until it hits the redirect limit and raises.
    raise ExternalProviderError(f"redirect loop fetching {url!r}")


class FetchResult:
    """Plain holder for `fetch_text` output. A small class instead of a
    dataclass so we can keep the import surface tight."""

    __slots__ = ("body", "byte_size", "content_type", "status", "url")

    def __init__(
        self, *, url: str, status: int, content_type: str, body: bytes, byte_size: int
    ) -> None:
        self.url = url
        self.status = status
        self.content_type = content_type
        self.body = body
        self.byte_size = byte_size


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    label: str,
    allow_status: tuple[int, ...] = (),
    **kwargs: Any,
) -> Any:
    """Issue a request and decode the response body as JSON.

    Wraps `httpx.HTTPError` and JSON decode failures into `ExternalProviderError`
    with a `{label} request failed` / `{label} returned non-json body` message
    so every provider raises the same error class on the same failure shapes.
    Status codes listed in `allow_status` short-circuit to `None` before
    `raise_for_status()` (used for FamilySearch endpoints that 404 when an
    optional resource is absent)."""
    try:
        response = await client.request(method, url, **kwargs)
        if response.status_code in allow_status:
            return None
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise ExternalProviderError(f"{label} request failed: {e}") from e
    try:
        return response.json()
    except ValueError as e:
        raise ExternalProviderError(f"{label} returned non-json body: {e}") from e


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_REDIRECTS",
    "DEFAULT_TEXT_CONTENT_TYPES",
    "DEFAULT_TIMEOUT_S",
    "DEFAULT_USER_AGENT",
    "FetchResult",
    "build_http_client",
    "fetch_text",
    "open_http_client",
    "request_json",
    "validate_url",
]
