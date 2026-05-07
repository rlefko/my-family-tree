"""Importing this module triggers tool registration on the global registry.
The MCP server and the in-process ToolHost both rely on import-time side
effects. Add new tool modules here so they're picked up automatically.

Note: `proposals` no longer registers tools directly. It exposes the shared
`make_proposal` helper used by the per-domain modules below."""

from my_family_tree.mcp.tools import (
    chunks,
    claims,
    conflicts,
    documents,
    events,
    external_ingest,
    genealogy,
    input,
    persons,
    places,
    relationships,
    sources,
    stats,
    web_search,
)

# Reference each module so the import-time side effects (registering tools on
# the global registry) aren't optimized away by ruff's unused-import lint.
__all__ = [
    "chunks",
    "claims",
    "conflicts",
    "documents",
    "events",
    "external_ingest",
    "genealogy",
    "input",
    "persons",
    "places",
    "relationships",
    "sources",
    "stats",
    "web_search",
]
