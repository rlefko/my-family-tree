"""Brave Search REST provider. https://api.search.brave.com/

Brave returns rich web results without redirecting through ad networks and
has a generous free tier. We map their `web.results` array onto the shared
`WebSearchResult` shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx
from pydantic import SecretStr

from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.external.http import build_http_client, request_json
from my_family_tree.external.web_search.base import WebSearchProvider, WebSearchResult

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


@dataclass(slots=True)
class BraveProvider(WebSearchProvider):
    api_key: SecretStr
    client: httpx.AsyncClient
    name: str = "brave"

    async def search(self, query: str, *, k: int) -> list[WebSearchResult]:
        params = {"q": query, "count": k}
        headers = {
            "X-Subscription-Token": self.api_key.get_secret_value(),
            "Accept": "application/json",
        }
        payload = await request_json(
            self.client,
            "GET",
            BRAVE_SEARCH_URL,
            label="brave",
            params=params,
            headers=headers,
        )
        web = payload.get("web") if isinstance(payload, dict) else None
        results = web.get("results") if isinstance(web, dict) else None
        if not isinstance(results, list):
            raise ExternalProviderError("brave response missing 'web.results' list")
        out: list[WebSearchResult] = []
        # Brave doesn't return per-result scores; we synthesize a descending
        # rank-based score so cross-provider sorting in the aggregator stays
        # well-defined.
        for index, raw in enumerate(results):
            if not isinstance(raw, dict):
                continue
            item = cast(dict[str, Any], raw)
            url = item.get("url")
            title = item.get("title") or ""
            description = item.get("description") or ""
            if not isinstance(url, str) or not url:
                continue
            out.append(
                WebSearchResult(
                    title=str(title),
                    url=url,
                    snippet=str(description),
                    score=max(0.0, 1.0 - (index / max(1, len(results)))),
                    provider=self.name,
                )
            )
        return out

    async def aclose(self) -> None:
        await self.client.aclose()


def build_brave_provider(*, api_key: SecretStr, timeout_s: float) -> BraveProvider:
    return BraveProvider(
        api_key=api_key,
        client=build_http_client(timeout_s=timeout_s),
    )
