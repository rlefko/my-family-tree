"""Tests for the OpenAI Responses-API stream-event translator. Real stream
events match the SDK's pydantic shapes, so we hand-build minimal duck-typed
stand-ins and assert the translator produces the right provider-neutral
StreamEvent sequence.

The translator's contract is the seam this whole pipeline lives or dies on:
- `response.output_item.added` (item.type=function_call) -> tool_use_started
- `response.function_call_arguments.delta`               -> tool_use_input_delta
- `response.function_call_arguments.done`                -> tool_use_finished
- `response.completed`                                   -> usage + done

Wrong event names here mean the agent loop never sees tool calls and reports
zero tokens, which is exactly the regression these tests prevent."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from my_family_tree.llm.base import Message, TextBlock, ToolResultBlock, ToolUseBlock
from my_family_tree.llm.openai_provider import _to_openai_input, _translate_openai_event


@dataclass
class _Raw:
    type: str
    delta: str = ""
    item: object | None = None
    item_id: str = ""
    response: object | None = None


@dataclass
class _Item:
    type: str
    id: str = ""
    call_id: str = ""
    name: str = ""


@dataclass
class _UsageDetails:
    cached_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    input_tokens_details: _UsageDetails | None = None
    output_tokens_details: _UsageDetails | None = None


@dataclass
class _Response:
    usage: _Usage | None = None
    error: object | None = None


@pytest.mark.unit
def test_text_delta_event_yields_text_delta() -> None:
    out = _translate_openai_event(_Raw(type="response.output_text.delta", delta="hi"), {})
    assert len(out) == 1
    assert out[0].type == "text_delta"
    assert out[0].text == "hi"


@pytest.mark.unit
def test_function_call_lifecycle_threads_call_id_through_args_events() -> None:
    """The added/delta/done events must all carry the same `call_id` so the
    agent loop can correlate them. Args events use `item_id`, so the
    translator must look up `item.id -> call_id` from the added event."""
    state: dict[str, str] = {}

    added = _Raw(
        type="response.output_item.added",
        item=_Item(
            type="function_call",
            id="item_abc",
            call_id="call_xyz",
            name="person_propose_create",
        ),
    )
    started = _translate_openai_event(added, state)
    assert len(started) == 1
    assert started[0].type == "tool_use_started"
    assert started[0].tool_use_id == "call_xyz"
    assert started[0].tool_name == "person_propose_create"
    assert state == {"item_abc": "call_xyz"}

    delta = _translate_openai_event(
        _Raw(type="response.function_call_arguments.delta", item_id="item_abc", delta='{"a":'),
        state,
    )
    assert len(delta) == 1
    assert delta[0].type == "tool_use_input_delta"
    assert delta[0].tool_use_id == "call_xyz"
    assert delta[0].tool_input_delta == '{"a":'

    done = _translate_openai_event(
        _Raw(type="response.function_call_arguments.done", item_id="item_abc"),
        state,
    )
    assert len(done) == 1
    assert done[0].type == "tool_use_finished"
    assert done[0].tool_use_id == "call_xyz"


@pytest.mark.unit
def test_response_completed_emits_usage_and_done() -> None:
    response = _Response(
        usage=_Usage(
            input_tokens=120,
            output_tokens=300,
            input_tokens_details=_UsageDetails(cached_tokens=40),
            output_tokens_details=_UsageDetails(reasoning_tokens=200),
        )
    )
    out = _translate_openai_event(_Raw(type="response.completed", response=response), {})
    types = [e.type for e in out]
    assert types == ["usage", "done"]
    usage = out[0].usage
    assert usage is not None
    assert usage.input_tokens == 120
    assert usage.output_tokens == 300
    assert usage.cached_input_tokens == 40
    assert usage.reasoning_tokens == 200


@pytest.mark.unit
def test_non_function_output_items_are_ignored() -> None:
    out = _translate_openai_event(
        _Raw(type="response.output_item.added", item=_Item(type="message")), {}
    )
    assert out == []


@pytest.mark.unit
def test_failed_response_emits_error_event() -> None:
    response = _Response(error="rate_limited")
    out = _translate_openai_event(_Raw(type="response.failed", response=response), {})
    assert len(out) == 1
    assert out[0].type == "error"
    assert "rate_limited" in (out[0].error_message or "")


@pytest.mark.unit
def test_unknown_event_type_yields_nothing() -> None:
    assert _translate_openai_event(_Raw(type="response.in_progress"), {}) == []


@pytest.mark.unit
def test_reasoning_summary_text_delta_yields_thinking_delta() -> None:
    out = _translate_openai_event(
        _Raw(type="response.reasoning_summary_text.delta", delta="Considering "), {}
    )
    assert len(out) == 1
    assert out[0].type == "thinking_delta"
    assert out[0].text == "Considering "


@pytest.mark.unit
def test_reasoning_summary_part_added_yields_thinking_break() -> None:
    """Each new reasoning summary part is a discrete semantic chunk; the
    translator must surface it as a `thinking_break` so the chat UI splits
    consecutive parts into separate collapsed blocks instead of merging them."""
    out = _translate_openai_event(_Raw(type="response.reasoning_summary_part.added"), {})
    assert len(out) == 1
    assert out[0].type == "thinking_break"


@pytest.mark.unit
def test_to_openai_input_emits_function_calls_as_top_level_items() -> None:
    """The Responses API rejects a `function_call` nested inside an assistant
    message's content array, so when we replay an assistant turn that
    contained a tool call, the tool_use must be hoisted to a top-level
    `function_call` item alongside the assistant's text message."""
    messages = [
        Message(role="user", content=[TextBlock(type="text", text="add a person")]),
        Message(
            role="assistant",
            content=[
                TextBlock(type="text", text="searching first"),
                ToolUseBlock(type="tool_use", id="call_1", name="person_search", input={"q": "x"}),
            ],
        ),
        Message(
            role="tool",
            content=[ToolResultBlock(type="tool_result", tool_use_id="call_1", output={"ok": 1})],
        ),
    ]
    out = _to_openai_input("system rules", messages)
    types = [item.get("type") or item.get("role") for item in out]
    assert types == [
        "system",
        "user",
        "assistant",
        "function_call",
        "function_call_output",
    ]
    fc = next(item for item in out if item.get("type") == "function_call")
    assert fc["call_id"] == "call_1"
    assert fc["name"] == "person_search"
    fco = next(item for item in out if item.get("type") == "function_call_output")
    assert fco["call_id"] == "call_1"


@pytest.mark.unit
def test_to_openai_input_assistant_with_only_tool_call_omits_empty_message() -> None:
    """An assistant message that is purely a tool call (no text) must not
    emit an empty `{role: assistant, content: []}` shell that the Responses
    API would reject."""
    messages = [
        Message(role="user", content=[TextBlock(type="text", text="hi")]),
        Message(
            role="assistant",
            content=[ToolUseBlock(type="tool_use", id="c1", name="t", input={})],
        ),
    ]
    out = _to_openai_input(None, messages)
    types = [item.get("type") or item.get("role") for item in out]
    assert types == ["user", "function_call"]
