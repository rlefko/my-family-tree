"""In-process ToolHost. Wraps the same handler functions the MCP server
registers, but with no transport overhead. Used by the chat agent so its hot
path doesn't pay JSON-over-loopback costs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_family_tree.core.errors import CapabilityDeniedError
from my_family_tree.core.logging import get_logger
from my_family_tree.mcp.registry import Capability, ToolRegistry

if TYPE_CHECKING:
    from my_family_tree.core.config import Settings
    from my_family_tree.external.genealogy import GenealogyService
    from my_family_tree.external.web_search import WebSearchService

    # Forward-declared so this module doesn't import the ingest service
    # (which lives in `services/external_ingest.py` and pulls in storage +
    # embedding clients) at type-check time.
    ExternalIngestService = Any

log = get_logger(__name__)


@dataclass(slots=True)
class ToolContext:
    """Per-call context handed to a tool handler. Carries the active DB session
    factory and the tree scope. Tools open their own transactional sessions.

    The optional `web_search`, `genealogy`, and `external_ingest` handles let
    tools hit external services without each handler re-resolving them from
    settings. They're `None` when their corresponding provider is disabled;
    the registry's `enabled_when` gating means the chat agent never sees a
    tool whose service is missing, but the fields stay typed-optional so
    tests can construct contexts without wiring full services."""

    session_factory: async_sessionmaker[AsyncSession]
    tree_id: UUID
    capabilities: Capability
    actor: str = "agent"
    agent_run_id: UUID | None = None
    web_search: WebSearchService | None = None
    genealogy: GenealogyService | None = None
    external_ingest: ExternalIngestService | None = None


class ToolHost:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        context: ToolContext,
        settings: Settings | None = None,
    ) -> None:
        self._registry = registry
        self._context = context
        self._settings = settings

    @property
    def context(self) -> ToolContext:
        return self._context

    def specs(self) -> list[dict[str, Any]]:
        """Tool specs filtered by the host's capabilities and the active
        settings (so tools whose provider is unconfigured are hidden).
        Suitable for shipping to a provider as the agent's tool catalog."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema(),
            }
            for t in self._registry.available(
                capability=self._context.capabilities, settings=self._settings
            )
        ]

    async def call(self, name: str, payload: dict[str, Any]) -> BaseModel:
        try:
            tool = self._registry.get(name, settings=self._settings)
        except KeyError as e:
            raise ValueError(f"unknown tool: {name}") from e
        if not tool.capability & self._context.capabilities:
            raise CapabilityDeniedError(
                f"tool {name!r} requires {tool.capability!s} "
                f"but host has {self._context.capabilities!s}"
            )
        validated = tool.input_model.model_validate(payload)
        log.debug("tool.call", name=name, tree_id=str(self._context.tree_id))
        return await tool.handler(self._context, validated)
