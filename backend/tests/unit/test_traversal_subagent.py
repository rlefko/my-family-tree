"""Unit tests for the traversal subagent runner.

The runner builds an inner `ChatAgent` whose tool host is read-only and
explicitly excludes `traverse_and_summarize` so the subagent cannot recurse
into itself. We use the `FakeProvider` pattern from `test_chat_agent_loop`
to drive the inner loop without an LLM, then assert on the result shape and
person-collection behavior."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_family_tree.agent.subagent_events import subagent_event_sink_scope
from my_family_tree.agent.traversal_subagent import (
    SubagentRunner,
    TraversalSubagentResult,
    TraversalSubagentRunner,
    _collect_persons,
    run_traversal_subagent,
)
from my_family_tree.llm.base import (
    Message,
    StreamEvent,
    UsageDelta,
)
from my_family_tree.mcp import tools as _tools_pkg  # noqa: F401  registers tools
from my_family_tree.mcp.host import ToolContext, ToolHost
from my_family_tree.mcp.registry import Capability, get_registry


@pytest.mark.unit
def test_runner_satisfies_subagent_runner_protocol() -> None:
    """`TraversalSubagentRunner` is the production implementation; a
    structural Protocol check guards against future drift between the
    concrete class and the abstract entry-point shape."""
    runner: SubagentRunner = TraversalSubagentRunner(
        provider=cast(Any, _NullProvider()),
        model="m",
    )
    assert hasattr(runner, "run_traversal")


@pytest.mark.unit
async def test_run_traversal_subagent_collects_text_into_summary() -> None:
    provider = _FakeProvider(
        scripts=[
            [_text("Found "), _text("two sons."), _usage(), _done()],
        ]
    )
    parent_ctx = _parent_ctx()
    result = await run_traversal_subagent(
        question="who are X's sons",
        person_id=uuid4(),
        max_generations=2,
        provider=cast(Any, provider),
        model="m",
        parent_ctx=parent_ctx,
    )
    assert isinstance(result, TraversalSubagentResult)
    assert result.summary == "Found two sons."
    assert result.persons == []


@pytest.mark.unit
async def test_run_traversal_subagent_records_token_usage() -> None:
    provider = _FakeProvider(
        scripts=[
            [_text("ok"), _usage(in_tokens=42, out_tokens=8), _done()],
        ]
    )
    result = await run_traversal_subagent(
        question="?",
        person_id=uuid4(),
        max_generations=1,
        provider=cast(Any, provider),
        model="m",
        parent_ctx=_parent_ctx(),
    )
    assert result.tokens_used == 50
    assert result.tool_calls_used == 0


@pytest.mark.unit
async def test_run_traversal_subagent_persists_text_in_trace() -> None:
    """Contiguous text deltas coalesce into a single text trace entry; the
    summary keeps the full text so the tool result carries both shapes."""
    provider = _FakeProvider(
        scripts=[
            [_text("Found "), _text("two sons."), _usage(), _done()],
        ]
    )
    result = await run_traversal_subagent(
        question="?",
        person_id=uuid4(),
        max_generations=1,
        provider=cast(Any, provider),
        model="m",
        parent_ctx=_parent_ctx(),
    )
    assert result.trace == [{"type": "text", "text": "Found two sons."}]


@pytest.mark.unit
async def test_run_traversal_subagent_persists_thinking_in_trace() -> None:
    """Thinking deltas coalesce into a thinking entry distinct from text; the
    user opted into persisting thinking so old turns rehydrate with the
    subagent's reasoning visible."""
    provider = _FakeProvider(
        scripts=[
            [
                StreamEvent(type="thinking_delta", text="Let me check "),
                StreamEvent(type="thinking_delta", text="the parents."),
                _text("Done."),
                _usage(),
                _done(),
            ],
        ]
    )
    result = await run_traversal_subagent(
        question="?",
        person_id=uuid4(),
        max_generations=1,
        provider=cast(Any, provider),
        model="m",
        parent_ctx=_parent_ctx(),
    )
    assert result.trace[0] == {"type": "thinking", "text": "Let me check the parents."}
    assert result.trace[1] == {"type": "text", "text": "Done."}


@pytest.mark.unit
async def test_run_traversal_subagent_splits_thinking_on_break() -> None:
    """A `thinking_break` between two thinking deltas seals the current
    consolidated entry so the next delta opens a new one. Forwards the same
    boundary on the sink so the live subagent stream splits into separate
    blocks."""
    provider = _FakeProvider(
        scripts=[
            [
                StreamEvent(type="thinking_delta", text="**Considering options**"),
                StreamEvent(type="thinking_break"),
                StreamEvent(type="thinking_delta", text="**Queueing**"),
                _text("Done."),
                _usage(),
                _done(),
            ],
        ]
    )
    captured: list[dict[str, Any]] = []

    class _CapturingSink:
        def emit(self, event: dict[str, Any]) -> None:
            captured.append(event)

    with subagent_event_sink_scope(_CapturingSink()):
        result = await run_traversal_subagent(
            question="?",
            person_id=uuid4(),
            max_generations=1,
            provider=cast(Any, provider),
            model="m",
            parent_ctx=_parent_ctx(),
        )

    assert result.trace[0] == {
        "type": "thinking",
        "text": "**Considering options**",
        "sealed": True,
    }
    assert result.trace[1] == {"type": "thinking", "text": "**Queueing**"}
    assert result.trace[2] == {"type": "text", "text": "Done."}

    types = [c["type"] for c in captured]
    assert types == ["thinking_delta", "thinking_break", "thinking_delta", "text_delta"]


@pytest.mark.unit
async def test_run_traversal_subagent_ignores_break_with_no_open_thinking_entry() -> None:
    """A `thinking_break` that arrives before any thinking text (or after a
    text/tool entry) must not seal anything or push a stray entry."""
    provider = _FakeProvider(
        scripts=[
            [
                StreamEvent(type="thinking_break"),
                _text("Done."),
                _usage(),
                _done(),
            ],
        ]
    )
    result = await run_traversal_subagent(
        question="?",
        person_id=uuid4(),
        max_generations=1,
        provider=cast(Any, provider),
        model="m",
        parent_ctx=_parent_ctx(),
    )
    assert result.trace == [{"type": "text", "text": "Done."}]


@pytest.mark.unit
async def test_run_traversal_subagent_records_open_tool_when_stream_truncates() -> None:
    """If a stream emits `tool_use_started` and an input delta but ends
    before the loop finishes the call, the trace still carries a tool entry
    with the name set so the parent UI can show the partial proof of work
    (input/output stay None)."""
    provider = _FakeProvider(
        scripts=[
            [
                StreamEvent(
                    type="tool_use_started",
                    tool_use_id="t1",
                    tool_name="person_search",
                ),
                StreamEvent(
                    type="tool_use_input_delta",
                    tool_use_id="t1",
                    tool_input_delta='{"query":"Anna"}',
                ),
            ],
        ]
    )
    result = await run_traversal_subagent(
        question="?",
        person_id=uuid4(),
        max_generations=1,
        provider=cast(Any, provider),
        model="m",
        parent_ctx=_parent_ctx(),
    )
    assert len(result.trace) == 1
    entry = result.trace[0]
    assert entry["type"] == "tool_use"
    assert entry["name"] == "person_search"
    assert entry["input"] is None
    assert entry["output"] is None


@pytest.mark.unit
async def test_run_traversal_subagent_emits_events_to_sink() -> None:
    """When a sink is installed via `subagent_event_sink_scope`, every inner
    text and thinking delta is forwarded so the parent loop can stream the
    proof of work to the UI as it happens."""
    provider = _FakeProvider(
        scripts=[
            [
                StreamEvent(type="thinking_delta", text="reasoning"),
                _text("Found 2."),
                _usage(),
                _done(),
            ],
        ]
    )
    captured: list[dict[str, Any]] = []

    class _CapturingSink:
        def emit(self, event: dict[str, Any]) -> None:
            captured.append(event)

    with subagent_event_sink_scope(_CapturingSink()):
        await run_traversal_subagent(
            question="?",
            person_id=uuid4(),
            max_generations=1,
            provider=cast(Any, provider),
            model="m",
            parent_ctx=_parent_ctx(),
        )

    types = [c["type"] for c in captured]
    assert "thinking_delta" in types
    assert "text_delta" in types
    # Order is preserved.
    assert types.index("thinking_delta") < types.index("text_delta")


@pytest.mark.unit
async def test_run_traversal_subagent_works_without_a_sink() -> None:
    """No sink installed: runner still records the trace and returns a
    well-formed result. Proves the contextvar default doesn't blow up."""
    provider = _FakeProvider(
        scripts=[
            [_text("ok"), _usage(), _done()],
        ]
    )
    result = await run_traversal_subagent(
        question="?",
        person_id=uuid4(),
        max_generations=1,
        provider=cast(Any, provider),
        model="m",
        parent_ctx=_parent_ctx(),
    )
    assert result.summary == "ok"
    assert result.trace == [{"type": "text", "text": "ok"}]


@pytest.mark.unit
async def test_run_traversal_subagent_returns_error_summary_on_provider_error() -> None:
    provider = _FakeProvider(
        scripts=[
            [
                StreamEvent(type="error", error_message="provider blew up"),
            ],
        ]
    )
    result = await run_traversal_subagent(
        question="?",
        person_id=uuid4(),
        max_generations=1,
        provider=cast(Any, provider),
        model="m",
        parent_ctx=_parent_ctx(),
    )
    assert "provider blew up" in result.summary


@pytest.mark.unit
def test_inner_host_excludes_traverse_and_summarize() -> None:
    """Build the same host shape `run_traversal_subagent` builds and verify
    the recursion guard: `traverse_and_summarize` must not appear in the
    inner agent's tool catalog."""
    parent_ctx = _parent_ctx()
    inner_ctx = ToolContext(
        session_factory=parent_ctx.session_factory,
        tree_id=parent_ctx.tree_id,
        capabilities=Capability.READ,
        actor="agent.traversal",
    )
    inner_host = ToolHost(
        get_registry(),
        context=inner_ctx,
        excluded_tools=frozenset({"traverse_and_summarize"}),
    )
    names = {spec["name"] for spec in inner_host.specs()}
    assert "traverse_and_summarize" not in names
    # Sanity: the read tools we need are still there.
    assert "person_relations" in names
    assert "person_count_relations" in names
    assert "person_traverse" in names


@pytest.mark.unit
def test_collect_persons_lifts_results_list() -> None:
    """`person_search` and `person_relations` use the flat
    `{"results": [...]}` shape; the collector must pick those up."""
    persons: dict[UUID, Any] = {}
    pid = uuid4()
    _collect_persons(
        {
            "results": [
                _person_summary_dict(pid, "Anna Doe"),
                {"id": "not-a-uuid", "ignored": True},
            ],
        },
        persons,
    )
    assert pid in persons
    assert persons[pid].display_name == "Anna Doe"


@pytest.mark.unit
def test_collect_persons_lifts_traverse_nodes() -> None:
    """`person_traverse` returns `{"nodes": [{"person": {...}, ...}, ...]}`;
    the collector must dive into the nested `person` block."""
    persons: dict[UUID, Any] = {}
    a, b = uuid4(), uuid4()
    _collect_persons(
        {
            "nodes": [
                {"person": _person_summary_dict(a, "A"), "generation": 0},
                {"person": _person_summary_dict(b, "B"), "generation": 1},
            ],
        },
        persons,
    )
    assert {a, b} <= persons.keys()


@pytest.mark.unit
def test_collect_persons_dedupes_by_id() -> None:
    persons: dict[UUID, Any] = {}
    pid = uuid4()
    payload = {"results": [_person_summary_dict(pid, "Anna Doe")]}
    _collect_persons(payload, persons)
    _collect_persons(payload, persons)
    assert len(persons) == 1


def _person_summary_dict(pid: UUID, name: str) -> dict[str, Any]:
    """Minimal `PersonSummary` shape that round-trips through Pydantic."""
    return {
        "id": str(pid),
        "display_name": name,
        "sex": "unknown",
        "birth": {"text": None, "min": None, "max": None, "precision": 0, "circa": False},
        "death": {"text": None, "min": None, "max": None, "precision": 0, "circa": False},
        "confidence": 100,
    }


def _parent_ctx() -> ToolContext:
    return ToolContext(
        session_factory=cast(async_sessionmaker[AsyncSession], _NullSessionFactory()),
        tree_id=uuid4(),
        capabilities=Capability.chat_default(),
    )


class _NullSessionFactory:
    """Stand-in for `async_sessionmaker[AsyncSession]`. The subagent does not
    open a session in these tests because we never let a tool actually run."""

    def __call__(self) -> Any:
        raise AssertionError("session factory should not be invoked under fake provider")


# --- FakeProvider machinery (mirrors test_chat_agent_loop) ----------------


@dataclass
class _FakeProvider:
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
        self.seen_messages.append(list(messages))
        events = self.scripts.pop(0) if self.scripts else []
        return _aiter(events)

    async def complete(self, **_: Any) -> Any:  # pragma: no cover  unused
        raise NotImplementedError


class _NullProvider:
    name = "null"
    default_model = "null-model"

    def stream(self, **_: Any) -> AsyncIterator[StreamEvent]:  # pragma: no cover  unused
        raise NotImplementedError

    async def complete(self, **_: Any) -> Any:  # pragma: no cover  unused
        raise NotImplementedError


async def _aiter(events: Iterable[StreamEvent]) -> AsyncIterator[StreamEvent]:
    for e in events:
        yield e


def _text(text: str) -> StreamEvent:
    return StreamEvent(type="text_delta", text=text)


def _usage(in_tokens: int = 10, out_tokens: int = 5) -> StreamEvent:
    return StreamEvent(
        type="usage",
        usage=UsageDelta(input_tokens=in_tokens, output_tokens=out_tokens),
    )


def _done() -> StreamEvent:
    return StreamEvent(type="done", stop_reason="end_turn")
