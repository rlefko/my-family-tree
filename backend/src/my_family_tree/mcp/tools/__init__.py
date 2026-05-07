"""Importing this module triggers tool registration on the global registry.
The MCP server and the in-process ToolHost both rely on import-time side
effects. Add new tool modules here so they're picked up automatically."""

from my_family_tree.mcp.tools import (
    chunks,
    conflicts,
    documents,
    persons,
    proposals,
    stats,
)
