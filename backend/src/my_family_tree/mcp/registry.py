"""Tool registry. Tools register themselves via `@registry.tool(...)`. The
registry is the single source of truth backing both the in-process `ToolHost`
and the MCP `Server` (stdio + Streamable HTTP)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from my_family_tree.core.config import Settings

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class Capability(Flag):
    """Capability bits used to gate which tools an agent can call."""

    READ = auto()
    PROPOSE = auto()
    WEB = auto()
    TRIVIAL_WRITE = auto()
    PRIVILEGED = auto()  # Reserved; not exposed via MCP

    @classmethod
    def all_read(cls) -> Capability:
        return cls.READ | cls.WEB

    @classmethod
    def chat_default(cls) -> Capability:
        return cls.READ | cls.PROPOSE | cls.TRIVIAL_WRITE | cls.WEB

    @classmethod
    def deep_research(cls) -> Capability:
        return cls.READ | cls.PROPOSE | cls.WEB | cls.TRIVIAL_WRITE


Handler = Callable[..., Awaitable[BaseModel]]
EnabledPredicate = Callable[["Settings"], bool]


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Handler
    capability: Capability
    is_read_only: bool = True
    enabled_when: EnabledPredicate | None = None

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()

    def is_available(self, settings: Settings | None) -> bool:
        """Return True when the tool can be called given the active settings.

        Tools without an `enabled_when` predicate are always available. When
        `settings is None` we conservatively return True so legacy callers
        (and tests that don't construct a full Settings) keep working."""
        if self.enabled_when is None or settings is None:
            return True
        return self.enabled_when(settings)


@dataclass(slots=True)
class ToolRegistry:
    tools: dict[str, ToolDefinition] = field(default_factory=dict)

    def tool(
        self,
        *,
        name: str,
        description: str,
        input_model: type[InputT],
        output_model: type[OutputT],
        capability: Capability,
        is_read_only: bool = True,
        enabled_when: EnabledPredicate | None = None,
    ) -> Callable[[Handler], Handler]:
        def decorator(fn: Handler) -> Handler:
            if name in self.tools:
                raise ValueError(f"duplicate tool name: {name}")
            self.tools[name] = ToolDefinition(
                name=name,
                description=description,
                input_model=input_model,
                output_model=output_model,
                handler=fn,
                capability=capability,
                is_read_only=is_read_only,
                enabled_when=enabled_when,
            )
            return fn

        return decorator

    def available(
        self,
        *,
        capability: Capability | None = None,
        settings: Settings | None = None,
    ) -> list[ToolDefinition]:
        """Return tools matching `capability` and currently available given
        `settings`. Tools whose `enabled_when` predicate returns False are
        filtered out; tools without a predicate or with `settings=None` are
        always included."""
        candidates = self.tools.values()
        if capability is not None:
            candidates = [t for t in candidates if t.capability & capability]
        if settings is not None:
            candidates = [t for t in candidates if t.is_available(settings)]
        return sorted(candidates, key=lambda t: t.name)

    def get(self, name: str, *, settings: Settings | None = None) -> ToolDefinition:
        """Look a tool up by name. When `settings` is supplied, raise
        `KeyError` for tools that exist but aren't currently available; this
        keeps the lookup contract uniform for both the in-process host and
        the external MCP server."""
        if name not in self.tools:
            raise KeyError(name)
        tool = self.tools[name]
        if settings is not None and not tool.is_available(settings):
            raise KeyError(name)
        return tool


_REGISTRY = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Return the process-wide registry. Tools register on import side-effect."""
    return _REGISTRY
