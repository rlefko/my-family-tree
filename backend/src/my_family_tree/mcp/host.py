"""In-process ToolHost. Wraps the same handler functions the MCP server
registers, but with no transport overhead. Used by the chat agent so its hot
path doesn't pay JSON-over-loopback costs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_family_tree.core.errors import CapabilityDeniedError
from my_family_tree.core.logging import get_logger
from my_family_tree.mcp.registry import Capability, ToolRegistry

# Cap on individual string fields and list lengths in `tool.start` log lines
# so a 200_000-char `note_create(body=...)` does not flood the log stream.
_LOG_STRING_MAX = 500
_LOG_LIST_MAX = 20

if TYPE_CHECKING:
    from my_family_tree.core.config import Settings
    from my_family_tree.embed.client import EmbeddingsClient
    from my_family_tree.external.genealogy import GenealogyService
    from my_family_tree.external.web_search import WebSearchService
    from my_family_tree.services.external_ingest import ExternalIngestService
    from my_family_tree.storage.s3 import ObjectStore

log = get_logger(__name__)


@dataclass(slots=True)
class ToolContext:
    """Per-call context handed to a tool handler. Carries the active DB session
    factory and the tree scope. Tools open their own transactional sessions.

    The optional `storage` and `embeddings` handles let tools that touch the
    knowledge base (notes, chunk search) reuse the long-lived clients without
    each handler re-resolving them from settings. The optional `web_search`,
    `genealogy`, and `external_ingest` handles do the same for external
    providers. All are `None` when their corresponding provider is disabled;
    the registry's `enabled_when` gating means the chat agent never sees a
    tool whose service is missing, but the fields stay typed-optional so
    tests can construct contexts without wiring full services."""

    session_factory: async_sessionmaker[AsyncSession]
    tree_id: UUID
    capabilities: Capability
    actor: str = "agent"
    agent_run_id: UUID | None = None
    storage: ObjectStore | None = None
    embeddings: EmbeddingsClient | None = None
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
        tree_id = str(self._context.tree_id)
        log.info(
            "tool.start",
            name=name,
            tree_id=tree_id,
            capability=str(tool.capability),
            input=_redact_for_log(validated),
        )
        started = time.perf_counter()
        try:
            result = await tool.handler(self._context, validated)
        except Exception as e:
            log.warning(
                "tool.end",
                name=name,
                tree_id=tree_id,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                ok=False,
                error=str(e),
            )
            raise
        log.info(
            "tool.end",
            name=name,
            tree_id=tree_id,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            ok=True,
        )
        return result


def _redact_for_log(model: BaseModel) -> dict[str, Any]:
    """Render a tool input model as a JSON-safe dict with long strings and
    long lists truncated. Walks recursively so a giant `body` buried inside
    a nested propose payload is still bounded."""
    return _redact(model.model_dump(mode="json"))


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > _LOG_STRING_MAX:
            return f"{value[:_LOG_STRING_MAX]}...<truncated {len(value) - _LOG_STRING_MAX} chars>"
        return value
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > _LOG_LIST_MAX:
            head = [_redact(v) for v in value[:_LOG_LIST_MAX]]
            head.append({"_truncated": f"{len(value) - _LOG_LIST_MAX} more items"})
            return head
        return [_redact(v) for v in value]
    return value
