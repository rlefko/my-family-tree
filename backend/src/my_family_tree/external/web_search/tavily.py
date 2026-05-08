"""Tavily web-search provider. https://docs.tavily.com/

Tavily is the default LLM-friendly REST search API. We use the `basic`
search depth to keep latency and cost predictable; callers asking for more
depth should switch the configured provider rather than threading per-call
flags through the MCP surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx
from pydantic import SecretStr

from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.external.http import build_http_client, request_json
from my_family_tree.external.web_search.base import WebSearchProvider, WebSearchResult

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


@dataclass(slots=True)
class TavilyProvider(WebSearchProvider):
    api_key: SecretStr
    client: httpx.AsyncClient
    name: str = "tavily"

    async def search(self, query: str, *, k: int) -> list[WebSearchResult]:
        body = {
            "api_key": self.api_key.get_secret_value(),
            "query": query,
            "max_results": k,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        payload = await request_json(
            self.client, "POST", TAVILY_SEARCH_URL, label="tavily", json=body
        )
        if not isinstance(payload, dict):
            raise ExternalProviderError("tavily response was not an object")
        results = payload.get("results")
        if not isinstance(results, list):
            raise ExternalProviderError("tavily response missing 'results' list")
        out: list[WebSearchResult] = []
        for raw in results:
            if not isinstance(raw, dict):
                continue
            item = cast(dict[str, Any], raw)
            url = item.get("url")
            title = item.get("title") or ""
            content = item.get("content") or ""
            score = item.get("score")
            if not isinstance(url, str) or not url:
                continue
            out.append(
                WebSearchResult(
                    title=str(title),
                    url=url,
                    snippet=str(content),
                    score=float(score) if isinstance(score, int | float) else 0.0,
                    provider=self.name,
                )
            )
        return out

    async def aclose(self) -> None:
        await self.client.aclose()


def build_tavily_provider(*, api_key: SecretStr, timeout_s: float) -> TavilyProvider:
    return TavilyProvider(
        api_key=api_key,
        client=build_http_client(timeout_s=timeout_s),
    )
