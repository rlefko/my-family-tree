"""Importing this module triggers tool registration on the global registry.
The MCP server and the in-process ToolHost both rely on import-time side
effects. Add new tool modules here so they're picked up automatically.

`proposals` registers a single cross-domain tool (`proposal_cancel`); the
per-domain propose-* tools live in their domain modules and reuse the
shared `make_proposal` helper from there."""

from my_family_tree.mcp.tools import (
    chunks,
    claims,
    conflicts,
    documents,
    events,
    external_ingest,
    genealogy,
    input,
    notes,
    persons,
    places,
    proposals,
    relationships,
    sources,
    stats,
    subagents,
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
    "notes",
    "persons",
    "places",
    "proposals",
    "relationships",
    "sources",
    "stats",
    "subagents",
    "web_search",
]
