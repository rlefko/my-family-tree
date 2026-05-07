"""`web_search` and `web_fetch` MCP tools.

`web_search` runs a query through the configured REST provider (Tavily or
Brave) and returns ranked hits. The tool is hidden from the catalog when
no provider is configured (`WebSearchView.is_enabled` is False).

`web_fetch` is unconditional but always passes through the SSRF + size +
content-type guards in `external/http.py`. It returns cleaned plain text
so the agent can read a specific URL without re-running a search."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from my_family_tree.core.errors import ExternalProviderError
from my_family_tree.external.fetch import fetch_url
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry

registry = get_registry()


# `web_fetch` returns at most this many characters of cleaned text. Beyond
# this we'd just be padding the LLM context with low-signal markup; the
# agent can re-fetch a different URL or reach into our knowledge base via
# `external_index_url` + `hybrid_search` when it needs more depth.
WEB_FETCH_MAX_CHARS = 50_000


class WebSearchResultOut(BaseModel):
    title: str
    url: str
    snippet: str
    score: float
    provider: str


class WebSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int | None = Field(default=None, ge=1, le=25)


class WebSearchOutput(BaseModel):
    results: list[WebSearchResultOut]
    provider: str


@registry.tool(
    name="web_search",
    description=(
        "Search the public web via the configured provider (Tavily or Brave). "
        "Returns ranked hits with title, url, and a short snippet. Use this to "
        "find external evidence (obituaries, vital records, news) the user "
        "hasn't uploaded. Cite the URL in any proposal grounded in a hit."
    ),
    input_model=WebSearchInput,
    output_model=WebSearchOutput,
    capability=Capability.WEB | Capability.READ,
    enabled_when=lambda s: s.web_search.is_enabled,
)
async def web_search(ctx: ToolContext, payload: WebSearchInput) -> WebSearchOutput:
    if ctx.web_search is None:
        raise ExternalProviderError("web_search service is not configured")
    hits = await ctx.web_search.search(payload.query, k=payload.k)
    return WebSearchOutput(
        provider=ctx.web_search.provider.name,
        results=[
            WebSearchResultOut(
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                score=hit.score,
                provider=hit.provider,
            )
            for hit in hits
        ],
    )


class WebFetchInput(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class WebFetchOutput(BaseModel):
    url: str
    title: str | None
    text: str
    fetched_at: datetime
    byte_size: int
    content_type: str
    truncated: bool


@registry.tool(
    name="web_fetch",
    description=(
        "Fetch a URL and return its main text content. Refuses non-public "
        "addresses, oversized responses, and non-text content types. The "
        "returned `text` is plain text with markup stripped; pair with "
        "`external_index_url` if you want the page in the searchable "
        "knowledge base for future calls."
    ),
    input_model=WebFetchInput,
    output_model=WebFetchOutput,
    capability=Capability.WEB | Capability.READ,
)
async def web_fetch(ctx: ToolContext, payload: WebFetchInput) -> WebFetchOutput:
    del ctx  # web_fetch has no service dependency; the http guards are unconditional.
    page = await fetch_url(payload.url)
    text = page.text
    truncated = False
    if len(text) > WEB_FETCH_MAX_CHARS:
        text = text[:WEB_FETCH_MAX_CHARS]
        truncated = True
    return WebFetchOutput(
        url=page.url,
        title=page.title,
        text=text,
        fetched_at=page.fetched_at,
        byte_size=page.byte_size,
        content_type=page.content_type,
        truncated=truncated,
    )
