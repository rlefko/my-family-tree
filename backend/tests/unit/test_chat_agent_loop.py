"""ChatAgent loop tests with a fake provider and a fake ToolHost.

The fake provider emits a scripted sequence of `StreamEvent`s. The fake host
records every `call(name, payload)` and returns a configurable result. We
assert ChatAgent surfaces the right `ChatTurnEvent`s and threads tool
results back through the next provider invocation."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any

import pytest

from my_family_tree.agent.budgets import Budgets
from my_family_tree.agent.loop import ChatAgent
from my_family_tree.api.routers.chat import _assistant_messages_from_content
from my_family_tree.llm.base import (
    Message,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UsageDelta,
)


@dataclass
class FakeHost:
    specs_list: list[dict[str, Any]] = field(default_factory=list)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    next_outputs: list[Any] = field(default_factory=list)

    def specs(self) -> list[dict[str, Any]]:
        return list(self.specs_list)

    async def call(self, name: str, payload: dict[str, Any]) -> Any:
        self.calls.append((name, payload))
        return self.next_outputs.pop(0) if self.next_outputs else _ProposalRefLike()


@dataclass
class _ProposalRefLike:
    proposal_id: str = "00000000-0000-0000-0000-0000000abc01"
    rationale: str = "test rationale"
    confidence: int = 70

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "rationale": self.rationale,
            "confidence": self.confidence,
        }


@dataclass
class FakeProvider:
    name: str = "fake"
    default_model: str = "fake-model"
    scripts: list[list[StreamEvent]] = field(default_factory=list)
    seen_messages: list[list[Message]] = field(default_factory=list)

    def stream(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[Message],
        tools: list[Any] | None = None,
        max_tokens: int = 4096,
        temperature: float | None = None,
        reasoning: Any = None,
        cache: Any = None,
    ) -> AsyncIterator[StreamEvent]:
        del model, system, tools, max_tokens, temperature, reasoning, cache
        # Snapshot the list so post-call mutations to the agent's `history`
        # don't leak into what we recorded for this stream call.
        self.seen_messages.append(list(messages))
        events = self.scripts.pop(0) if self.scripts else []
        return _aiter(events)

    async def complete(self, **_: Any) -> Any:  # pragma: no cover  unused in tests
        raise NotImplementedError


async def _aiter(events: Iterable[StreamEvent]) -> AsyncIterator[StreamEvent]:
    for e in events:
        yield e


def _text(t: str) -> StreamEvent:
    return StreamEvent(type="text_delta", text=t)


def _tool_started(call_id: str, name: str) -> StreamEvent:
    return StreamEvent(type="tool_use_started", tool_use_id=call_id, tool_name=name)


def _tool_input(call_id: str, delta: str) -> StreamEvent:
    return StreamEvent(type="tool_use_input_delta", tool_use_id=call_id, tool_input_delta=delta)


def _tool_finished(call_id: str) -> StreamEvent:
    return StreamEvent(type="tool_use_finished", tool_use_id=call_id)


def _usage(in_tokens: int = 50, out_tokens: int = 25) -> StreamEvent:
    return StreamEvent(
        type="usage",
        usage=UsageDelta(input_tokens=in_tokens, output_tokens=out_tokens),
    )


def _done() -> StreamEvent:
    return StreamEvent(type="done", stop_reason="end_turn")


def _initial_messages() -> list[Message]:
    return [Message(role="user", content=[TextBlock(type="text", text="hi")])]


@pytest.mark.unit
async def test_text_only_turn_emits_deltas_and_done() -> None:
    provider = FakeProvider(scripts=[[_text("Hello"), _text(" world"), _usage(), _done()]])
    host = FakeHost()
    agent = ChatAgent(provider=provider, model="m", host=host, budgets=Budgets())
    events = []
    async for evt in agent.run_turn(_initial_messages()):
        events.append((evt.type, evt.payload))
    types = [e[0] for e in events]
    assert types == ["text_delta", "text_delta", "usage", "done"]
    text = "".join(e[1].get("text", "") for e in events if e[0] == "text_delta")
    assert text == "Hello world"
    done = next(e[1] for e in events if e[0] == "done")
    assert done["proposal_ids"] == []


@pytest.mark.unit
async def test_tool_call_dispatches_into_host_and_threads_result_back() -> None:
    """The provider terminates every successful stream with `done`. The agent
    must still re-enter the provider on the next turn to give the model a
    chance to respond to tool results, instead of bailing out on the first
    `done`."""
    args = {"display_name": "Test Person"}
    args_json = json.dumps(args)
    first_turn = [
        _tool_started("call_1", "person_propose_create"),
        _tool_input("call_1", args_json),
        _tool_finished("call_1"),
        _usage(),
        _done(),
    ]
    second_turn = [_text("Queued 1 proposal"), _usage(), _done()]
    provider = FakeProvider(scripts=[first_turn, second_turn])
    host = FakeHost(next_outputs=[_ProposalRefLike(proposal_id="aaa")])
    agent = ChatAgent(provider=provider, model="m", host=host, budgets=Budgets())

    events = []
    async for evt in agent.run_turn(_initial_messages()):
        events.append((evt.type, evt.payload))

    # Host received the call with parsed args.
    assert host.calls == [("person_propose_create", args)]

    # The agent emitted tool_use_started, tool_use_finished, tool_result, then
    # text_delta and done on the second pass.
    types = [e[0] for e in events]
    assert "tool_use_started" in types
    assert "tool_use_finished" in types
    assert "tool_result" in types
    assert "done" in types

    # Done event surfaces the proposal_id from the tool result.
    done = next(e[1] for e in events if e[0] == "done")
    assert done["proposal_ids"] == ["aaa"]

    # The second provider invocation saw the assistant turn + tool result in history.
    assert len(provider.seen_messages) == 2
    second_history = provider.seen_messages[1]
    assert any(m.role == "assistant" for m in second_history)
    assert any(m.role == "tool" for m in second_history)


@pytest.mark.unit
async def test_tool_error_marks_result_as_error_and_continues() -> None:
    first_turn = [
        _tool_started("call_1", "person_propose_create"),
        _tool_input("call_1", "{}"),
        _tool_finished("call_1"),
        _usage(),
        _done(),
    ]
    second_turn = [_text("oops"), _done()]

    class _ExplodingHost(FakeHost):
        async def call(self, name: str, payload: dict[str, Any]) -> Any:
            self.calls.append((name, payload))
            raise RuntimeError("kaboom")

    provider = FakeProvider(scripts=[first_turn, second_turn])
    host = _ExplodingHost()
    agent = ChatAgent(provider=provider, model="m", host=host, budgets=Budgets())

    events = []
    async for evt in agent.run_turn(_initial_messages()):
        events.append((evt.type, evt.payload))

    tool_result = next(e[1] for e in events if e[0] == "tool_result")
    assert tool_result["is_error"] is True
    assert "kaboom" in str(tool_result["output"])
    done = next(e[1] for e in events if e[0] == "done")
    assert done["proposal_ids"] == []  # error tool never contributes a proposal id


@pytest.mark.unit
async def test_tool_with_malformed_json_input_surfaces_real_error_without_host_call() -> None:
    """When the model's tool-call argument JSON arrives truncated (typically
    because `max_output_tokens` cut the stream off mid-string), the agent must
    NOT hand the garbage to the host. Instead it should emit an `is_error=True`
    tool_result whose output names the likely cause so the agent can recover
    on the next pass with a shorter payload."""
    first_turn = [
        _tool_started("call_1", "person_propose_create"),
        # Deliberately missing the closing brace, so json.loads raises.
        _tool_input("call_1", '{"display_name": "Jane Doe"'),
        _tool_finished("call_1"),
        _usage(),
        _done(),
    ]
    second_turn = [_text("retrying with a smaller payload"), _done()]
    provider = FakeProvider(scripts=[first_turn, second_turn])
    host = FakeHost()
    agent = ChatAgent(provider=provider, model="m", host=host, budgets=Budgets())

    events = []
    async for evt in agent.run_turn(_initial_messages()):
        events.append((evt.type, evt.payload))

    # The host was never invoked with the half-parsed JSON.
    assert host.calls == []

    tool_result = next(e[1] for e in events if e[0] == "tool_result")
    assert tool_result["is_error"] is True
    error_text = str(tool_result["output"]).lower()
    assert "max_output_tokens" in error_text or "truncated" in error_text

    # The error result is threaded back into history so the model has a chance
    # to react on the next provider call.
    assert len(provider.seen_messages) == 2
    second_history = provider.seen_messages[1]
    assert any(m.role == "assistant" for m in second_history)
    assert any(m.role == "tool" for m in second_history)


@pytest.mark.unit
async def test_second_turn_sees_prior_tool_history_via_rehydrated_messages() -> None:
    """The bug being fixed: each turn used to start blind because
    `_history_messages` stripped tool calls when reloading the conversation.
    With the splitter in place, the persisted assistant `content_json` for a
    prior turn rehydrates into the assistant tool_use + tool tool_result pair
    the providers expect, so the second turn's first stream call already
    sees the agent's earlier `person_search` and the canonical id it found.
    """
    persisted_assistant_content = [
        {
            "type": "tool_use",
            "id": "call_anna_search",
            "name": "person_search",
            "input": {"query": "Anna"},
            "output": {"results": [{"id": "p-anna", "display_name": "Anna Doe"}]},
            "is_error": False,
        },
        {"type": "text", "text": "Found Anna."},
    ]
    rehydrated = _assistant_messages_from_content(persisted_assistant_content)
    assert [m.role for m in rehydrated] == ["assistant", "tool"]

    history: list[Message] = [
        Message(role="user", content=[TextBlock(type="text", text="Search for Anna.")]),
        *rehydrated,
        Message(
            role="user",
            content=[TextBlock(type="text", text="Anna's birthday is January 1, 1950.")],
        ),
    ]
    provider = FakeProvider(scripts=[[_text("Queued an event."), _usage(), _done()]])
    host = FakeHost()
    agent = ChatAgent(provider=provider, model="m", host=host, budgets=Budgets())

    async for _ in agent.run_turn(history):
        pass

    seen = provider.seen_messages[0]
    assistant_msgs = [m for m in seen if m.role == "assistant"]
    tool_msgs = [m for m in seen if m.role == "tool"]
    assert len(assistant_msgs) == 1
    assert len(tool_msgs) == 1

    use_block = next(b for b in assistant_msgs[0].content if isinstance(b, ToolUseBlock))
    assert use_block.id == "call_anna_search"
    assert use_block.name == "person_search"
    assert use_block.input == {"query": "Anna"}

    result_block = next(
        b for b in tool_msgs[0].content if isinstance(b, ToolResultBlock)
    )
    assert result_block.tool_use_id == "call_anna_search"
    assert result_block.output == {
        "results": [{"id": "p-anna", "display_name": "Anna Doe"}]
    }
    assert result_block.is_error is False

    # The agent did not re-call person_search: with prior results visible in
    # history, the host received nothing on this turn.
    assert host.calls == []
