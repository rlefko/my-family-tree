"""MCP server. Registers every tool from the global registry on the official
`mcp` SDK server. Two transports are supported: stdio (for Claude Desktop)
and Streamable HTTP (mounted under FastAPI in prod, also stand-alone in dev).
"""

from __future__ import annotations

import json
import sys
from typing import Any
from uuid import UUID

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from sqlalchemy.ext.asyncio import async_sessionmaker

from my_family_tree.core.logging import get_logger
from my_family_tree.mcp.host import ToolContext
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.tools import (  # noqa: F401  side-effect: register tools
    chunks,
    conflicts,
    documents,
    persons,
    proposals,
    stats,
)

log = get_logger(__name__)


def build_mcp_server(
    *,
    session_factory: async_sessionmaker,
    tree_id: UUID,
    capability: Capability = Capability.READ,
) -> Any:
    """Build the MCP server. Returns the SDK's Server instance."""
    server: Any = Server("my-family-tree")
    registry = get_registry()

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.input_schema(),
            )
            for t in registry.available(capability=capability)
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        tool = registry.get(name)
        if not tool.capability & capability:
            raise PermissionError(
                f"tool {name!r} requires {tool.capability!s}; server has {capability!s}"
            )
        ctx = ToolContext(
            session_factory=session_factory,
            tree_id=tree_id,
            capabilities=capability,
            actor="mcp_external",
        )
        validated = tool.input_model.model_validate(arguments)
        result = await tool.handler(ctx, validated)
        return [TextContent(type="text", text=result.model_dump_json())]

    return server


async def run_stdio(
    *,
    session_factory: async_sessionmaker,
    tree_id: UUID,
    capability: Capability = Capability.READ,
) -> None:
    """Run the MCP server over stdio (for Claude Desktop and similar clients)."""
    server = build_mcp_server(
        session_factory=session_factory, tree_id=tree_id, capability=capability
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


# Re-export so `from my_family_tree.mcp.server import build_mcp_server, run_stdio` works.
__all__ = ["build_mcp_server", "run_stdio"]


# Tiny helper used by tests to assert tool wiring without spinning up MCP.
def registered_tool_names() -> list[str]:
    return [t.name for t in get_registry().available()]


def _smoke() -> None:
    """Invoked from the CLI to validate registry wiring; prints the catalog."""
    catalog = [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema(),
            "capability": str(t.capability),
        }
        for t in get_registry().available()
    ]
    sys.stdout.write(json.dumps(catalog, indent=2) + "\n")
