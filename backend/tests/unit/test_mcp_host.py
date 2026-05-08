"""ToolHost logging tests.

The host emits `tool.start` and `tool.end` structlog events around every
handler call. We use `structlog.testing.capture_logs()` to lock that
contract in: success goes through `tool.end` with `ok=True`, failure goes
through `tool.end` with `ok=False`, and long input strings are truncated
in the start log so a 200_000-char `note_create(body=...)` can't flood the
log stream."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import pytest
import structlog
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from my_family_tree.mcp.host import ToolContext, ToolHost, _redact_for_log
from my_family_tree.mcp.registry import Capability, ToolRegistry


class _FakeIn(BaseModel):
    text: str = ""
    items: list[str] = []
    nested: dict[str, Any] = {}


class _FakeOut(BaseModel):
    echoed: str = ""


def _build_host(handler: Any) -> ToolHost:
    registry = ToolRegistry()
    registry.tool(
        name="fake_echo",
        description="Echo the input back",
        input_model=_FakeIn,
        output_model=_FakeOut,
        capability=Capability.READ,
    )(handler)
    ctx = ToolContext(
        session_factory=cast(async_sessionmaker[AsyncSession], None),
        tree_id=UUID("00000000-0000-0000-0000-000000000001"),
        capabilities=Capability.READ,
    )
    return ToolHost(registry, context=ctx)


@pytest.mark.unit
async def test_successful_call_emits_start_then_end_with_duration() -> None:
    async def handler(_ctx: ToolContext, payload: _FakeIn) -> _FakeOut:
        return _FakeOut(echoed=payload.text)

    host = _build_host(handler)
    with structlog.testing.capture_logs() as logs:
        result = await host.call("fake_echo", {"text": "hi"})

    assert isinstance(result, _FakeOut)
    events = [r["event"] for r in logs]
    assert events == ["tool.start", "tool.end"]

    start = logs[0]
    assert start["name"] == "fake_echo"
    assert start["tree_id"] == "00000000-0000-0000-0000-000000000001"
    assert start["capability"] == str(Capability.READ)
    assert start["input"] == {"text": "hi", "items": [], "nested": {}}

    end = logs[1]
    assert end["name"] == "fake_echo"
    assert end["ok"] is True
    assert isinstance(end["duration_ms"], float)
    assert end["duration_ms"] >= 0


@pytest.mark.unit
async def test_failing_handler_logs_end_with_error_and_propagates() -> None:
    async def handler(_ctx: ToolContext, _payload: _FakeIn) -> _FakeOut:
        raise RuntimeError("kaboom")

    host = _build_host(handler)
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(RuntimeError, match="kaboom"):
            await host.call("fake_echo", {})

    events = [r["event"] for r in logs]
    assert events == ["tool.start", "tool.end"]
    end = logs[1]
    assert end["ok"] is False
    assert end["error"] == "kaboom"
    assert isinstance(end["duration_ms"], float)


@pytest.mark.unit
def test_redact_for_log_truncates_long_strings_at_top_level() -> None:
    payload = _FakeIn(text="x" * 1000)
    redacted = _redact_for_log(payload)
    assert redacted["text"].startswith("x" * 500)
    assert "<truncated 500 chars>" in redacted["text"]


@pytest.mark.unit
def test_redact_for_log_walks_into_nested_dicts_and_lists() -> None:
    payload = _FakeIn(
        items=[f"item-{i}" for i in range(50)],
        nested={"deep": {"body": "y" * 800}},
    )
    redacted = _redact_for_log(payload)

    assert len(redacted["items"]) == 21
    assert redacted["items"][-1] == {"_truncated": "30 more items"}

    deep = redacted["nested"]["deep"]["body"]
    assert deep.startswith("y" * 500)
    assert "<truncated 300 chars>" in deep
