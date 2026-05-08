"""`GenealogyService` aggregates search across whichever genealogy
providers are enabled and dispatches per-provider get-by-id calls.

Each provider is independent; if one fails we log and keep going so a
single misbehaving provider doesn't take down the whole search."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from my_family_tree.core.config import GenealogyView
from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.core.logging import get_logger
from my_family_tree.external.genealogy.base import (
    GenealogyHit,
    GenealogyProfile,
    GenealogyProvider,
)
from my_family_tree.external.genealogy.familysearch import build_familysearch_provider
from my_family_tree.external.genealogy.wikidata import build_wikidata_provider
from my_family_tree.external.genealogy.wikitree import build_wikitree_provider

log = get_logger(__name__)


@dataclass(slots=True)
class GenealogyService:
    providers: dict[str, GenealogyProvider]
    default_max_results: int

    @classmethod
    def from_settings(cls, settings: GenealogyView) -> GenealogyService | None:
        providers: dict[str, GenealogyProvider] = {}
        if settings.wikitree_enabled:
            providers["wikitree"] = build_wikitree_provider(
                user_agent=settings.genealogy_user_agent,
                timeout_s=settings.request_timeout_s,
            )
        if settings.wikidata_enabled:
            providers["wikidata"] = build_wikidata_provider(
                user_agent=settings.genealogy_user_agent,
                timeout_s=settings.request_timeout_s,
            )
        if settings.familysearch_enabled:
            assert settings.familysearch_client_id is not None
            assert settings.familysearch_client_secret is not None
            providers["familysearch"] = build_familysearch_provider(
                client_id=settings.familysearch_client_id,
                client_secret=settings.familysearch_client_secret,
                environment=settings.familysearch_environment,
                timeout_s=settings.request_timeout_s,
                user_agent=settings.genealogy_user_agent,
            )
        if not providers:
            return None
        return cls(providers=providers, default_max_results=settings.max_results)

    def has(self, provider: str) -> bool:
        return provider in self.providers

    async def search(
        self,
        query: str,
        *,
        k: int | None = None,
        birth_year: int | None = None,
        death_year: int | None = None,
        place: str | None = None,
    ) -> list[GenealogyHit]:
        limit = k or self.default_max_results
        if limit < 1:
            raise ExternalProviderError("k must be >= 1")
        per_provider_k = max(1, limit)
        coros = [
            self._safe_search(provider, query, per_provider_k, birth_year, death_year, place)
            for provider in self.providers.values()
        ]
        results_per_provider = await asyncio.gather(*coros)
        merged: list[GenealogyHit] = []
        for hits in results_per_provider:
            merged.extend(hits)
        merged.sort(key=lambda hit: hit.score, reverse=True)
        return merged[:limit]

    async def get_person(self, provider: str, provider_id: str) -> GenealogyProfile:
        impl = self.providers.get(provider)
        if impl is None:
            raise ExternalProviderError(f"genealogy provider {provider!r} not enabled")
        return await impl.get_person(provider_id)

    async def aclose(self) -> None:
        await asyncio.gather(*(p.aclose() for p in self.providers.values()))

    async def _safe_search(
        self,
        provider: GenealogyProvider,
        query: str,
        k: int,
        birth_year: int | None,
        death_year: int | None,
        place: str | None,
    ) -> list[GenealogyHit]:
        try:
            return await provider.search(
                query,
                k=k,
                birth_year=birth_year,
                death_year=death_year,
                place=place,
            )
        except Exception as e:
            log.warning(
                "genealogy.search_failed",
                provider=provider.name,
                error=str(e),
            )
            return []
