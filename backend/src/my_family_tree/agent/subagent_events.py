"""Subagent event sink. The chat agent's loop installs a sink before awaiting
a tool call that may run a subagent; the subagent reads the sink off a
contextvar and forwards each inner event to it. The loop drains the sink in
parallel with the tool task and yields wrapped `subagent_event` ChatTurnEvents
so the SSE client and the persistence layer can both observe the inner work.

Using a contextvar keeps leaf tools free of LLM coupling: only code that
explicitly opts into the sink (today, just `run_traversal_subagent`) ever
reads it. Tasks created via `asyncio.create_task` inherit the contextvar
snapshot from the calling scope, so the loop's `_execute_tool` task sees the
sink the loop installed without any extra wiring."""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol


class SubagentEventSink(Protocol):
    """Minimal sink protocol. Subagents call `emit` for each inner event;
    the loop's draining coroutine pulls them out and yields them upstream."""

    def emit(self, event: dict[str, Any]) -> None: ...


_sink_var: contextvars.ContextVar[SubagentEventSink | None] = contextvars.ContextVar(
    "mft_subagent_event_sink",
    default=None,
)


def get_subagent_event_sink() -> SubagentEventSink | None:
    """Return the sink installed by the closest enclosing `subagent_event_sink_scope`,
    or `None` when no sink is active. Subagent runners call this once per run
    and forward inner events to the returned sink (if any)."""
    return _sink_var.get()


@contextmanager
def subagent_event_sink_scope(sink: SubagentEventSink | None) -> Iterator[None]:
    """Install `sink` as the current subagent event sink for the duration of
    the with-block. Resets to the prior sink (usually `None`) on exit, even
    when an exception propagates."""
    token = _sink_var.set(sink)
    try:
        yield
    finally:
        _sink_var.reset(token)
