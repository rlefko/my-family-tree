"""Tests for the Tavily and Brave web-search providers and the
`WebSearchService.from_settings` selector.

Mocks the underlying httpx calls via respx so the suite stays offline."""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from pydantic import SecretStr

from my_family_tree.core.config import WebSearchView
from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.external.web_search.brave import BRAVE_SEARCH_URL, build_brave_provider
from my_family_tree.external.web_search.service import WebSearchService
from my_family_tree.external.web_search.tavily import TAVILY_SEARCH_URL, build_tavily_provider


def _view(provider: str = "", **overrides: object) -> WebSearchView:
    defaults: dict[str, object] = {
        "provider": provider,
        "tavily_api_key": None,
        "brave_api_key": None,
        "max_results": 5,
        "request_timeout_s": 5.0,
        "max_bytes": 5_000_000,
    }
    defaults.update(overrides)
    return WebSearchView(**defaults)  # type: ignore[arg-type]


@pytest.mark.unit
@respx.mock
async def test_tavily_provider_returns_results() -> None:
    respx.post(TAVILY_SEARCH_URL).mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {
                        "title": "John Doe Obituary",
                        "url": "https://example.com/jd",
                        "content": "Born 1900...",
                        "score": 0.91,
                    }
                ]
            },
        )
    )
    provider = build_tavily_provider(api_key=SecretStr("tk_test"), timeout_s=2.0)
    try:
        results = await provider.search("john doe", k=3)
    finally:
        await provider.aclose()
    assert len(results) == 1
    hit = results[0]
    assert hit.url == "https://example.com/jd"
    assert hit.title == "John Doe Obituary"
    assert hit.score == pytest.approx(0.91)
    assert hit.provider == "tavily"


@pytest.mark.unit
@respx.mock
async def test_tavily_propagates_http_error() -> None:
    respx.post(TAVILY_SEARCH_URL).mock(return_value=Response(500))
    provider = build_tavily_provider(api_key=SecretStr("tk"), timeout_s=2.0)
    try:
        with pytest.raises(ExternalProviderError):
            await provider.search("x", k=1)
    finally:
        await provider.aclose()


@pytest.mark.unit
@respx.mock
async def test_brave_provider_returns_results() -> None:
    respx.get(BRAVE_SEARCH_URL).mock(
        return_value=Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Hit 1",
                            "url": "https://a.example",
                            "description": "snippet 1",
                        },
                        {
                            "title": "Hit 2",
                            "url": "https://b.example",
                            "description": "snippet 2",
                        },
                    ]
                }
            },
        )
    )
    provider = build_brave_provider(api_key=SecretStr("bk_test"), timeout_s=2.0)
    try:
        results = await provider.search("anything", k=2)
    finally:
        await provider.aclose()
    assert [r.url for r in results] == ["https://a.example", "https://b.example"]
    # Brave doesn't return scores, so we should get a descending rank-based score.
    assert results[0].score > results[1].score


@pytest.mark.unit
@respx.mock
async def test_brave_handles_malformed_payload() -> None:
    respx.get(BRAVE_SEARCH_URL).mock(return_value=Response(200, json={"oops": True}))
    provider = build_brave_provider(api_key=SecretStr("bk"), timeout_s=2.0)
    try:
        with pytest.raises(ExternalProviderError, match="missing"):
            await provider.search("x", k=1)
    finally:
        await provider.aclose()


@pytest.mark.unit
def test_service_from_settings_returns_none_when_disabled() -> None:
    assert WebSearchService.from_settings(_view()) is None
    assert WebSearchService.from_settings(_view(provider="openai_native")) is None


@pytest.mark.unit
def test_service_from_settings_returns_none_when_key_missing() -> None:
    # provider set to tavily but no key
    assert WebSearchService.from_settings(_view(provider="tavily")) is None
    # provider set to brave but no key
    assert WebSearchService.from_settings(_view(provider="brave")) is None


@pytest.mark.unit
def test_service_from_settings_picks_tavily() -> None:
    service = WebSearchService.from_settings(
        _view(provider="tavily", tavily_api_key=SecretStr("tk"))
    )
    assert service is not None
    assert service.provider.name == "tavily"


@pytest.mark.unit
def test_service_from_settings_picks_brave() -> None:
    service = WebSearchService.from_settings(_view(provider="brave", brave_api_key=SecretStr("bk")))
    assert service is not None
    assert service.provider.name == "brave"
