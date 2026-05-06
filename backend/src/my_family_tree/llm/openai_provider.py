"""OpenAI adapter. Targets the Responses API with reasoning + tools.

Streaming events are translated to provider-neutral `StreamEvent`s. We persist
only summaries of reasoning, never raw thinking text."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

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
from my_family_tree.llm.reasoning import OPENAI_EFFORT_FALLBACKS

log = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-5.5"

    def __init__(self, client: AsyncOpenAI, *, default_model: str = "gpt-5.5") -> None:
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
        """Drain the stream into a single result. Useful for non-streaming callers."""
        del cache  # OpenAI handles caching automatically
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
        del cache
        request: dict[str, Any] = {
            "model": model,
            "input": _to_openai_input(system, messages),
            "max_output_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                }
                for t in tools
            ]
        if temperature is not None:
            request["temperature"] = temperature
        if reasoning is not None and reasoning.effort != "none":
            request["reasoning"] = {
                "effort": OPENAI_EFFORT_FALLBACKS[reasoning.effort],
            }

        return _stream_iter(self._client, request)


async def _stream_iter(client: AsyncOpenAI, request: dict[str, Any]) -> AsyncIterator[StreamEvent]:
    try:
        stream = await client.responses.create(**request)
    except Exception as e:
        raise LLMProviderError(f"openai responses.create failed: {e}") from e

    async for raw in stream:
        for event in _translate_openai_event(raw):
            yield event


def _to_openai_input(system: str | None, messages: list[Message]) -> list[dict[str, Any]]:
    """Convert provider-neutral messages to OpenAI Responses input format."""
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    for msg in messages:
        if msg.role == "tool":
            for block in msg.content:
                if isinstance(block, ToolResultBlock):
                    out.append(
                        {
                            "type": "function_call_output",
                            "call_id": block.tool_use_id,
                            "output": _stringify_output(block.output),
                        }
                    )
            continue

        parts: list[dict[str, Any]] = []
        for block in msg.content:
            if isinstance(block, TextBlock):
                parts.append(
                    {
                        "type": "input_text" if msg.role == "user" else "output_text",
                        "text": block.text,
                    }
                )
            elif isinstance(block, ToolUseBlock):
                parts.append(
                    {
                        "type": "function_call",
                        "call_id": block.id,
                        "name": block.name,
                        "arguments": _stringify_output(block.input),
                    }
                )
        out.append({"role": msg.role, "content": parts})
    return out


def _stringify_output(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _translate_openai_event(raw: Any) -> list[StreamEvent]:
    """Translate one raw OpenAI stream event into zero or more StreamEvents."""
    events: list[StreamEvent] = []
    event_type = getattr(raw, "type", None)
    if event_type == "response.output_text.delta":
        events.append(StreamEvent(type="text_delta", text=getattr(raw, "delta", "")))
    elif event_type == "response.function_call.added":
        events.append(
            StreamEvent(
                type="tool_use_started",
                tool_use_id=getattr(raw, "call_id", ""),
                tool_name=getattr(raw, "name", ""),
            )
        )
    elif event_type == "response.function_call.delta":
        events.append(
            StreamEvent(
                type="tool_use_input_delta",
                tool_use_id=getattr(raw, "call_id", ""),
                tool_input_delta=getattr(raw, "delta", ""),
            )
        )
    elif event_type == "response.function_call.completed":
        events.append(
            StreamEvent(
                type="tool_use_finished",
                tool_use_id=getattr(raw, "call_id", ""),
            )
        )
    elif event_type == "response.completed":
        usage_obj = getattr(raw, "usage", None)
        if usage_obj is not None:
            events.append(
                StreamEvent(
                    type="usage",
                    usage=UsageDelta(
                        input_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
                        output_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
                        reasoning_tokens=getattr(usage_obj, "reasoning_tokens", 0) or 0,
                    ),
                )
            )
        events.append(StreamEvent(type="done", stop_reason="end_turn"))
    return events
