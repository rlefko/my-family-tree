"""`WebSearchService` selects a single provider based on Settings.

The service is `None` (constructible only via `from_settings`) when no
provider is configured, which is the gating signal MCP tools read via
`enabled_when` predicates."""

from __future__ import annotations

from dataclasses import dataclass

from my_family_tree.core.config import WebSearchView
from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.core.logging import get_logger
from my_family_tree.external.web_search.base import WebSearchProvider, WebSearchResult
from my_family_tree.external.web_search.brave import build_brave_provider
from my_family_tree.external.web_search.tavily import build_tavily_provider

log = get_logger(__name__)


@dataclass(slots=True)
class WebSearchService:
    provider: WebSearchProvider
    default_max_results: int

    @classmethod
    def from_settings(cls, settings: WebSearchView) -> WebSearchService | None:
        """Construct a service if a REST provider is configured, else None.

        The literal `provider in {"openai_native", "anthropic_native"}` cases
        intentionally fall through to `None` here: those flags gate in-LLM
        search calls handled by the provider SDK, not the MCP `web_search`
        tool."""
        if not settings.is_enabled:
            return None
        if settings.provider == "tavily":
            if settings.tavily_api_key is None:
                return None
            return cls(
                provider=build_tavily_provider(
                    api_key=settings.tavily_api_key,
                    timeout_s=settings.request_timeout_s,
                ),
                default_max_results=settings.max_results,
            )
        if settings.provider == "brave":
            if settings.brave_api_key is None:
                return None
            return cls(
                provider=build_brave_provider(
                    api_key=settings.brave_api_key,
                    timeout_s=settings.request_timeout_s,
                ),
                default_max_results=settings.max_results,
            )
        return None

    async def search(self, query: str, *, k: int | None = None) -> list[WebSearchResult]:
        limit = k or self.default_max_results
        if limit < 1:
            raise ExternalProviderError("k must be >= 1")
        results = await self.provider.search(query, k=limit)
        log.info(
            "web_search.completed",
            provider=self.provider.name,
            query=query,
            returned=len(results),
        )
        return results

    async def aclose(self) -> None:
        await self.provider.aclose()
