"""Provider-neutral types for web-search results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    score: float
    provider: str


class WebSearchProvider(Protocol):
    """Single-method interface every web-search backend implements."""

    name: str

    async def search(self, query: str, *, k: int) -> list[WebSearchResult]: ...

    async def aclose(self) -> None: ...
