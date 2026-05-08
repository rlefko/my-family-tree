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
    ImageBlock,
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
    default_model = "gpt-5"

    def __init__(self, client: AsyncOpenAI, *, default_model: str = "gpt-5") -> None:
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
                except json.JSONDecodeError as e:
                    # Truncated tool-call arguments: fail loudly instead of
                    # wrapping in `{"_raw": ...}`, which would silently hand
                    # garbage to the caller. The streaming agent loop has its
                    # own structured recovery; the non-streaming `complete()`
                    # surface should report the failure outright.
                    raise LLMProviderError(
                        f"openai tool-call arguments for {current_tool['name']!r} "
                        f"could not be parsed: {e}"
                    ) from e
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
                # Ask for an auto-summarized reasoning trace so the chat UI
                # can show a "thinking..." pill while the model deliberates.
                "summary": "auto",
            }

        return _stream_iter(self._client, request)


async def _stream_iter(client: AsyncOpenAI, request: dict[str, Any]) -> AsyncIterator[StreamEvent]:
    try:
        stream = await client.responses.create(**request)
    except Exception as e:
        raise LLMProviderError(f"openai responses.create failed: {e}") from e

    # Responses-API streaming uses two ids for a function call: `item.id`
    # (referenced by the args delta/done events as `item_id`) and `item.call_id`
    # (the id the model expects on the function_call_output we send back).
    # We translate every event to use the public-facing call_id so the agent
    # loop's tool tracking lines up across started/delta/finished.
    item_to_call_id: dict[str, str] = {}

    async for raw in stream:
        for event in _translate_openai_event(raw, item_to_call_id):
            yield event


def _to_openai_input(system: str | None, messages: list[Message]) -> list[dict[str, Any]]:
    """Convert provider-neutral messages to OpenAI Responses input format.

    The Responses API treats `function_call` and `function_call_output` as
    top-level input items, not content-parts inside a role-message. So when an
    assistant message contains a tool_use, we emit a text-only message (if it
    has any text) followed by separate `function_call` items."""
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

        text_parts: list[dict[str, Any]] = []
        function_calls: list[dict[str, Any]] = []
        for block in msg.content:
            if isinstance(block, TextBlock):
                text_parts.append(
                    {
                        "type": "input_text" if msg.role == "user" else "output_text",
                        "text": block.text,
                    }
                )
            elif isinstance(block, ImageBlock):
                # Images are only meaningful on user content; assistant images
                # are not generated by this app, so we skip them silently if
                # they appear on a non-user role.
                if msg.role == "user":
                    text_parts.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:{block.media_type};base64,{block.data_b64}",
                        }
                    )
            elif isinstance(block, ToolUseBlock):
                function_calls.append(
                    {
                        "type": "function_call",
                        "call_id": block.id,
                        "name": block.name,
                        "arguments": _stringify_output(block.input),
                    }
                )
        if text_parts:
            out.append({"role": msg.role, "content": text_parts})
        out.extend(function_calls)
    return out


def _stringify_output(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _translate_openai_event(raw: Any, item_to_call_id: dict[str, str]) -> list[StreamEvent]:
    """Translate one raw OpenAI Responses-API stream event into zero or more
    provider-neutral StreamEvents. `item_to_call_id` is mutable per-stream
    state used to map `item_id` (referenced by the args delta/done events) to
    the public `call_id` the agent loop tracks."""
    events: list[StreamEvent] = []
    event_type = getattr(raw, "type", None)

    if event_type == "response.output_text.delta":
        events.append(StreamEvent(type="text_delta", text=getattr(raw, "delta", "")))

    elif event_type in (
        "response.reasoning_summary_text.delta",
        "response.reasoning_text.delta",
    ):
        # Surface a redacted reasoning summary to the chat UI so the user has
        # a "thinking..." pill instead of a silent dead-air gap while the
        # model burns reasoning tokens. Only the SUMMARY text is forwarded;
        # raw reasoning is never persisted.
        events.append(StreamEvent(type="thinking_delta", text=getattr(raw, "delta", "") or ""))

    elif event_type == "response.output_item.added":
        item = getattr(raw, "item", None)
        if item is not None and getattr(item, "type", None) == "function_call":
            item_id = getattr(item, "id", None) or ""
            call_id = getattr(item, "call_id", "") or ""
            if item_id:
                item_to_call_id[item_id] = call_id
            events.append(
                StreamEvent(
                    type="tool_use_started",
                    tool_use_id=call_id,
                    tool_name=getattr(item, "name", "") or "",
                )
            )

    elif event_type == "response.function_call_arguments.delta":
        item_id = getattr(raw, "item_id", "") or ""
        call_id = item_to_call_id.get(item_id, item_id)
        events.append(
            StreamEvent(
                type="tool_use_input_delta",
                tool_use_id=call_id,
                tool_input_delta=getattr(raw, "delta", "") or "",
            )
        )

    elif event_type == "response.function_call_arguments.done":
        item_id = getattr(raw, "item_id", "") or ""
        call_id = item_to_call_id.get(item_id, item_id)
        events.append(
            StreamEvent(
                type="tool_use_finished",
                tool_use_id=call_id,
            )
        )

    elif event_type == "response.completed":
        response = getattr(raw, "response", None)
        usage_obj = getattr(response, "usage", None) if response is not None else None
        if usage_obj is not None:
            input_details = getattr(usage_obj, "input_tokens_details", None)
            output_details = getattr(usage_obj, "output_tokens_details", None)
            cached = (getattr(input_details, "cached_tokens", 0) or 0) if input_details else 0
            reasoning = (
                (getattr(output_details, "reasoning_tokens", 0) or 0) if output_details else 0
            )
            events.append(
                StreamEvent(
                    type="usage",
                    usage=UsageDelta(
                        input_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
                        output_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
                        cached_input_tokens=cached,
                        reasoning_tokens=reasoning,
                    ),
                )
            )
        events.append(StreamEvent(type="done", stop_reason="end_turn"))

    elif event_type in ("response.failed", "response.incomplete"):
        response = getattr(raw, "response", None)
        error = getattr(response, "error", None) if response is not None else None
        events.append(
            StreamEvent(
                type="error",
                error_message=str(error) if error is not None else event_type,
            )
        )

    elif event_type == "error":
        events.append(
            StreamEvent(
                type="error",
                error_message=str(getattr(raw, "message", "openai stream error")),
            )
        )

    return events
