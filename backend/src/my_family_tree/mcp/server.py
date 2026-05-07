"""MCP server. Registers every tool from the global registry on the official
`mcp` SDK server. Two transports are supported:

- stdio  (for Claude Desktop and similar local clients)
- Streamable HTTP (for the web app and other remote clients)

Both transports share the same low-level `Server` and the same tool registry."""

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import uvicorn
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import TextContent, Tool
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

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


def build_streamable_http_app(
    *,
    session_factory: async_sessionmaker,
    tree_id: UUID,
    capability: Capability = Capability.READ,
    stateless: bool = False,
) -> Starlette:
    """Build a Starlette ASGI app that serves the MCP server over Streamable
    HTTP at `/mcp` plus a `/healthz` probe.

    Set `stateless=True` for a fan-out deployment without sticky sessions;
    otherwise pin clients to a single task with ALB cookie stickiness (see
    `infra/terraform/modules/alb/main.tf`)."""
    server = build_mcp_server(
        session_factory=session_factory, tree_id=tree_id, capability=capability
    )
    manager = StreamableHTTPSessionManager(app=server, stateless=stateless)

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "transport": "streamable-http"})

    @asynccontextmanager
    async def lifespan(_: Starlette) -> Any:
        async with manager.run():
            log.info("mcp.streamable_http.ready")
            yield
            log.info("mcp.streamable_http.shutdown")

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/healthz", healthz),
            Mount("/mcp", app=manager.handle_request),
        ],
    )


def run_streamable_http(
    *,
    session_factory: async_sessionmaker,
    tree_id: UUID,
    capability: Capability = Capability.READ,
    host: str = "0.0.0.0",
    port: int = 8765,
    stateless: bool = False,
) -> None:
    """Run the MCP Streamable HTTP server via uvicorn."""
    app = build_streamable_http_app(
        session_factory=session_factory,
        tree_id=tree_id,
        capability=capability,
        stateless=stateless,
    )
    uvicorn.run(app, host=host, port=port, log_config=None)


__all__ = [
    "build_mcp_server",
    "build_streamable_http_app",
    "run_stdio",
    "run_streamable_http",
]


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
