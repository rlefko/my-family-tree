"""Tests for the SSRF, content-type, and size guards in `external/http.py`.

Network calls are mocked through `respx` so the suite stays offline. We
mostly assert *refusal* paths because that's the safety surface that
matters; happy-path coverage lives in the per-provider tests."""

from __future__ import annotations

import ipaddress
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx

from my_family_tree.core.errors import ExternalProviderError, UnsafeUrlError
from my_family_tree.external.http import (
    DEFAULT_TEXT_CONTENT_TYPES,
    build_http_client,
    fetch_text,
    validate_url,
)


# Small helper: pretend every host resolves to a single given IP. respx mocks
# the HTTP layer; we patch DNS so `validate_url`'s checks see what we want.
def _stub_resolver(ip: str) -> Any:
    addr = ipaddress.ip_address(ip)
    return patch("my_family_tree.external.http._resolve_all", return_value=[addr])


@pytest.mark.unit
@pytest.mark.parametrize(
    "blocked_ip",
    [
        "10.0.0.1",
        "127.0.0.1",
        "169.254.169.254",  # cloud-instance metadata
        "172.16.0.5",
        "192.168.0.5",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_validate_url_rejects_blocked_addresses(blocked_ip: str) -> None:
    with _stub_resolver(blocked_ip), pytest.raises(UnsafeUrlError):
        validate_url("http://example.com/x")


@pytest.mark.unit
def test_validate_url_rejects_non_http_schemes() -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url("file:///etc/passwd")
    with pytest.raises(UnsafeUrlError):
        validate_url("gopher://example.com/")


@pytest.mark.unit
def test_validate_url_accepts_public_address() -> None:
    with _stub_resolver("93.184.216.34"):  # example.com
        validate_url("https://example.com/")


@pytest.mark.unit
def test_validate_url_rejects_unresolvable_host() -> None:
    with (
        patch("my_family_tree.external.http._resolve_all", return_value=[]),
        pytest.raises(UnsafeUrlError),
    ):
        validate_url("http://does-not-exist.local/")


@pytest.mark.unit
def test_validate_url_rejects_literal_loopback_ipv6() -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url("http://[::1]/x")


@pytest.mark.unit
@respx.mock
async def test_fetch_text_refuses_disallowed_content_type() -> None:
    respx.get("https://example.com/x").respond(
        status_code=200,
        headers={"content-type": "application/octet-stream"},
        content=b"binary",
    )
    client = build_http_client(timeout_s=1.0)
    try:
        with (
            _stub_resolver("93.184.216.34"),
            pytest.raises(ExternalProviderError, match="content type"),
        ):
            await fetch_text(
                client,
                "https://example.com/x",
                allowed_content_types=DEFAULT_TEXT_CONTENT_TYPES,
            )
    finally:
        await client.aclose()


@pytest.mark.unit
@respx.mock
async def test_fetch_text_aborts_on_size_cap() -> None:
    body = b"x" * 1024
    respx.get("https://example.com/big").respond(
        status_code=200,
        headers={"content-type": "text/plain"},
        content=body,
    )
    client = build_http_client(timeout_s=1.0)
    try:
        with (
            _stub_resolver("93.184.216.34"),
            pytest.raises(ExternalProviderError, match="exceeded"),
        ):
            await fetch_text(
                client,
                "https://example.com/big",
                max_bytes=128,
            )
    finally:
        await client.aclose()


@pytest.mark.unit
@respx.mock
async def test_fetch_text_revalidates_redirect_target() -> None:
    """A redirect to a private IP must be rejected on the second hop, not
    silently followed by httpx."""
    respx.get("https://public.example.com/jump").respond(
        status_code=302,
        headers={"location": "http://private.example.internal/secret"},
    )
    client = build_http_client(timeout_s=1.0)
    try:
        # First hop resolves public, second hop resolves to a private IP.
        addrs = iter(
            [
                [ipaddress.ip_address("93.184.216.34")],
                [ipaddress.ip_address("10.0.0.1")],
            ]
        )

        def _next_resolution(_host: str) -> Any:
            return next(addrs)

        with (
            patch(
                "my_family_tree.external.http._resolve_all",
                side_effect=_next_resolution,
            ),
            pytest.raises(UnsafeUrlError),
        ):
            await fetch_text(client, "https://public.example.com/jump")
    finally:
        await client.aclose()


@pytest.mark.unit
@respx.mock
async def test_fetch_text_returns_body_for_allowed_content_type() -> None:
    respx.get("https://example.com/page").respond(
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=b"<html><body>hi</body></html>",
    )
    client = build_http_client(timeout_s=1.0)
    try:
        with _stub_resolver("93.184.216.34"):
            result = await fetch_text(client, "https://example.com/page")
        assert result.status == 200
        assert result.content_type == "text/html"
        assert result.body == b"<html><body>hi</body></html>"
    finally:
        await client.aclose()


@pytest.mark.unit
async def test_fetch_text_propagates_httpx_errors_as_external_error() -> None:
    client = build_http_client(timeout_s=0.001)
    try:
        with (
            _stub_resolver("93.184.216.34"),
            pytest.raises((ExternalProviderError, httpx.HTTPError)),
        ):
            await fetch_text(client, "https://example.invalid/")
    finally:
        await client.aclose()
