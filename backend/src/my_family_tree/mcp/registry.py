"""Tool registry. Tools register themselves via `@registry.tool(...)`. The
registry is the single source of truth backing both the in-process `ToolHost`
and the MCP `Server` (stdio + Streamable HTTP)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import Any, TypeVar

from pydantic import BaseModel

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


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Handler
    capability: Capability
    is_read_only: bool = True

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()


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
            )
            return fn

        return decorator

    def available(self, *, capability: Capability | None = None) -> list[ToolDefinition]:
        if capability is None:
            return sorted(self.tools.values(), key=lambda t: t.name)
        return sorted(
            (t for t in self.tools.values() if t.capability & capability),
            key=lambda t: t.name,
        )

    def get(self, name: str) -> ToolDefinition:
        if name not in self.tools:
            raise KeyError(name)
        return self.tools[name]


_REGISTRY = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Return the process-wide registry. Tools register on import side-effect."""
    return _REGISTRY
