"""Provider-neutral primitives. Adapters in `openai_provider.py` and
`anthropic_provider.py` translate to/from these."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh"]


@dataclass(slots=True)
class TextBlock:
    type: Literal["text"]
    text: str


@dataclass(slots=True)
class ImageBlock:
    type: Literal["image"]
    media_type: str
    data_b64: str


@dataclass(slots=True)
class ToolUseBlock:
    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, Any]


@dataclass(slots=True)
class ToolResultBlock:
    type: Literal["tool_result"]
    tool_use_id: str
    output: Any
    is_error: bool = False


@dataclass(slots=True)
class ThinkingBlock:
    type: Literal["thinking"]
    summary: str
    tokens: int = 0


ContentBlock = TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock


@dataclass(slots=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: list[ContentBlock]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    """JSON Schema for the tool's input."""


@dataclass(slots=True)
class ReasoningConfig:
    effort: ReasoningEffort = "medium"
    """Maps to OpenAI `reasoning.effort` and Anthropic extended thinking budget."""


@dataclass(slots=True)
class CacheConfig:
    """Anthropic prompt caching hint. OpenAI ignores."""

    cache_system: bool = True
    cache_tools: bool = True


@dataclass(slots=True)
class UsageDelta:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass(slots=True)
class StreamEvent:
    type: Literal[
        "text_delta",
        "thinking_delta",
        "tool_use_started",
        "tool_use_input_delta",
        "tool_use_finished",
        "usage",
        "done",
        "error",
    ]
    text: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input_delta: str | None = None
    tool_input: dict[str, Any] | None = None
    usage: UsageDelta | None = None
    stop_reason: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class CompletionResult:
    blocks: list[ContentBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = ""
    provider: str = ""
    usage: UsageDelta = field(default_factory=UsageDelta)


class LLMProvider(Protocol):
    """Streaming-first interface. `complete()` is a thin wrapper that drains
    the stream into a `CompletionResult`."""

    name: str
    default_model: str

    async def complete(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
        reasoning: ReasoningConfig | None = None,
        cache: CacheConfig | None = None,
    ) -> CompletionResult: ...

    def stream(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
        reasoning: ReasoningConfig | None = None,
        cache: CacheConfig | None = None,
    ) -> AsyncIterator[StreamEvent]: ...
