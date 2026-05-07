"""Anthropic adapter. Targets the Messages API with extended thinking and
ephemeral prompt caching. Streaming events are translated to provider-neutral
`StreamEvent`s. Raw thinking content is not persisted; we keep summaries only."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic

from my_family_tree.core.errors import LLMProviderError
from my_family_tree.core.logging import get_logger
from my_family_tree.llm.base import (
    CacheConfig,
    CompletionResult,
    LLMProvider,
    Message,
    ReasoningConfig,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
    UsageDelta,
)
from my_family_tree.llm.reasoning import ANTHROPIC_THINKING_BUDGET

log = get_logger(__name__)


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-opus-4-7"

    def __init__(self, client: AsyncAnthropic, *, default_model: str = "claude-opus-4-7") -> None:
        self._client = client
        self.default_model = default_model

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
    ) -> CompletionResult:
        result = CompletionResult(model=model, provider=self.name)
        current_text: list[str] = []
        current_tool: dict[str, Any] | None = None

        async for event in self.stream(
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning=reasoning,
            cache=cache,
        ):
            if event.type == "text_delta" and event.text:
                current_text.append(event.text)
            elif event.type == "tool_use_started":
                if current_text:
                    result.blocks.append(TextBlock(type="text", text="".join(current_text)))
                    current_text.clear()
                current_tool = {
                    "id": event.tool_use_id,
                    "name": event.tool_name,
                    "input": "",
                }
            elif event.type == "tool_use_input_delta" and current_tool is not None:
                current_tool["input"] += event.tool_input_delta or ""
            elif event.type == "tool_use_finished" and current_tool is not None:
                try:
                    parsed = json.loads(current_tool["input"]) if current_tool["input"] else {}
                except json.JSONDecodeError:
                    parsed = {"_raw": current_tool["input"]}
                result.blocks.append(
                    ToolUseBlock(
                        type="tool_use",
                        id=current_tool["id"],
                        name=current_tool["name"],
                        input=parsed,
                    )
                )
                current_tool = None
            elif event.type == "usage" and event.usage:
                result.usage = event.usage
            elif event.type == "done":
                result.stop_reason = event.stop_reason or "end_turn"

        if current_text:
            result.blocks.append(TextBlock(type="text", text="".join(current_text)))
        return result

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
    ) -> AsyncIterator[StreamEvent]:
        return _stream_iter(
            self._client,
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning=reasoning,
            cache=cache,
        )


async def _stream_iter(
    client: AsyncAnthropic,
    *,
    model: str,
    system: str | None,
    messages: list[Message],
    tools: list[ToolSpec] | None,
    max_tokens: int,
    temperature: float | None,
    reasoning: ReasoningConfig | None,
    cache: CacheConfig | None,
) -> AsyncIterator[StreamEvent]:
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": _to_anthropic_messages(messages),
    }
    if system:
        if cache and cache.cache_system:
            request["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            request["system"] = system
    if tools:
        request["tools"] = _to_anthropic_tools(tools, cache=cache)
    if temperature is not None:
        request["temperature"] = temperature
    if reasoning is not None:
        budget = ANTHROPIC_THINKING_BUDGET.get(reasoning.effort)
        if budget is not None:
            request["thinking"] = {"type": "enabled", "budget_tokens": budget}

    try:
        async with client.messages.stream(**request) as stream:
            async for raw in stream:
                for event in _translate_anthropic_event(raw):
                    yield event
    except Exception as e:
        raise LLMProviderError(f"anthropic messages.stream failed: {e}") from e


def _to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.role
        if role == "system":
            continue  # handled at top level
        if role == "tool":
            content_blocks: list[dict[str, Any]] = []
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    content_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.tool_use_id,
                            "content": _stringify(block.output),
                            "is_error": block.is_error,
                        }
                    )
            out.append({"role": "user", "content": content_blocks})
            continue

        content_blocks = []
        for block in msg.content:
            if isinstance(block, TextBlock):
                content_blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
        out.append({"role": role, "content": content_blocks})
    return out


def _to_anthropic_tools(
    tools: list[ToolSpec], *, cache: CacheConfig | None
) -> list[dict[str, Any]]:
    converted = [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in tools
    ]
    if cache and cache.cache_tools and converted:
        converted[-1]["cache_control"] = {"type": "ephemeral"}
    return converted


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _translate_anthropic_event(raw: Any) -> list[StreamEvent]:
    """Translate one Anthropic stream event into zero or more StreamEvents."""
    events: list[StreamEvent] = []
    event_type = getattr(raw, "type", None)
    if event_type == "content_block_start":
        block = getattr(raw, "content_block", None)
        block_type = getattr(block, "type", None)
        if block_type == "tool_use":
            events.append(
                StreamEvent(
                    type="tool_use_started",
                    tool_use_id=getattr(block, "id", ""),
                    tool_name=getattr(block, "name", ""),
                )
            )
    elif event_type == "content_block_delta":
        delta = getattr(raw, "delta", None)
        delta_type = getattr(delta, "type", None)
        if delta_type == "text_delta":
            events.append(StreamEvent(type="text_delta", text=getattr(delta, "text", "")))
        elif delta_type == "input_json_delta":
            events.append(
                StreamEvent(
                    type="tool_use_input_delta",
                    tool_input_delta=getattr(delta, "partial_json", ""),
                )
            )
        elif delta_type == "thinking_delta":
            events.append(StreamEvent(type="thinking_delta", text=getattr(delta, "thinking", "")))
    elif event_type == "content_block_stop":
        events.append(StreamEvent(type="tool_use_finished"))
    elif event_type == "message_delta":
        usage_obj = getattr(raw, "usage", None)
        if usage_obj is not None:
            events.append(
                StreamEvent(
                    type="usage",
                    usage=UsageDelta(
                        input_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
                        output_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
                        cached_input_tokens=getattr(usage_obj, "cache_read_input_tokens", 0) or 0,
                    ),
                )
            )
    elif event_type == "message_stop":
        events.append(StreamEvent(type="done", stop_reason="end_turn"))
    return events
