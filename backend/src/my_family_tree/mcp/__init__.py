"""MCP layer.

`registry` is the single source of truth for tools. `host` wraps the registry
for in-process callers (the chat agent). `server` exposes the same registry
over the official MCP SDK (stdio + Streamable HTTP) so external clients like
Claude Desktop can use it too. Read tools commit nothing; write tools create
`proposal` rows that the user (or an explicit auto-approve policy) approves
via the API."""

from my_family_tree.mcp.host import ToolContext, ToolHost
from my_family_tree.mcp.registry import (
    Capability,
    ToolDefinition,
    ToolRegistry,
    get_registry,
)

__all__ = [
    "Capability",
    "ToolContext",
    "ToolDefinition",
    "ToolHost",
    "ToolRegistry",
    "get_registry",
]
