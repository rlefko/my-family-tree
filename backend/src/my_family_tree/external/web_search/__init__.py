"""Web-search providers behind a shared `WebSearchService` interface.

Two REST providers are wired up: Tavily and Brave. The provider literal
strings `openai_native` and `anthropic_native` (also legal in
`WEB_SEARCH_PROVIDER`) gate in-LLM tool calls handled by the LLM SDK
itself, not the MCP `web_search` tool, so they intentionally don't
construct a service here."""

from my_family_tree.external.web_search.base import WebSearchProvider, WebSearchResult
from my_family_tree.external.web_search.service import WebSearchService

__all__ = ["WebSearchProvider", "WebSearchResult", "WebSearchService"]
