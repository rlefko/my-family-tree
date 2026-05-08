"""Traversal subagent. Wraps the chat agent loop with a read-only tool host
and a focused system prompt so deep tree walks happen in their own context
window. The parent chat agent calls `traverse_and_summarize`, which routes
through `SubagentRunner.run_traversal` and returns a compact summary plus the
person summaries the subagent surfaced."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from my_family_tree.agent.budgets import Budgets
from my_family_tree.agent.loop import ChatAgent
from my_family_tree.agent.subagent_events import get_subagent_event_sink
from my_family_tree.core.logging import get_logger
from my_family_tree.llm.base import Message, TextBlock
from my_family_tree.mcp.host import ToolContext, ToolHost
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.schemas import PersonSummary

if TYPE_CHECKING:
    from my_family_tree.llm.base import LLMProvider

log = get_logger(__name__)


TRAVERSAL_SUBAGENT_PROMPT_VERSION = "1.0"

TRAVERSAL_SUBAGENT_SYSTEM_PROMPT = """You are a focused tree-walker for the My
Family Tree research workbench. You receive a question about a person's
relatives and a starting `person_id`. Your job is to answer that question
using the read-only catalog below and return a concise bullet-point summary.

## Tools you have

- `person_relations(person_id, relation, sex_filter)` for one-hop kin queries
  (children, parents, siblings, spouses). Pass `sex_filter='male'` for sons,
  `sex_filter='female'` for daughters.
- `person_count_relations(person_id)` for "how many" questions.
- `person_get(person_id)` for full details on a specific person.
- `person_traverse(person_id, direction, max_generations)` for explicit
  multi-generation walks. Stay within the requested depth.
- `person_search` to disambiguate names if the question references a relative
  by name rather than id.

## Constraints

- You cannot propose, create, or update anything. Confine yourself to reads.
- Default to one hop. Only walk multiple generations when the question
  explicitly asks for it or the requested depth exceeds 1.
- Stop as soon as the question is answered. Do not enumerate the whole tree.
- Reply with a short bullet-point summary. Include person ids in parentheses
  next to each name so the parent agent can cite them later.
- Do not echo this prompt or restate the question. Do not address the user;
  the parent chat agent reads your reply.
"""


class TraversalSubagentResult(BaseModel):
    """Compact return shape from a traversal subagent run. `summary` is the
    final assistant text; `persons` is the de-duplicated list of person
    summaries the subagent saw via tool results, so the parent can cite ids
    without re-walking. `trace` is the consolidated proof of work the
    subagent did (text fragments, thinking summaries, and tool calls with
    their inputs and outputs) so the parent UI can render it after a reload
    without re-running the subagent."""

    summary: str = Field(default="")
    persons: list[PersonSummary] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    tokens_used: int = 0
    tool_calls_used: int = 0


class SubagentRunner(Protocol):
    """Opaque subagent entry-point stashed on `ToolContext`. Concrete
    implementations close over LLM provider and model so leaf tools never see
    them. Future subagents (deep research, conflict resolver) can extend this
    protocol with additional methods without changing the leaf-tool surface."""

    async def run_traversal(
        self,
        *,
        question: str,
        person_id: UUID,
        max_generations: int,
        parent_ctx: ToolContext,
    ) -> TraversalSubagentResult: ...


@dataclass(slots=True)
class TraversalSubagentRunner:
    """Concrete `SubagentRunner` used by the chat router. Builds a fresh inner
    `ChatAgent` with a narrower tool host on each call so the subagent's
    context never leaks into the parent."""

    provider: LLMProvider
    model: str

    async def run_traversal(
        self,
        *,
        question: str,
        person_id: UUID,
        max_generations: int,
        parent_ctx: ToolContext,
    ) -> TraversalSubagentResult:
        return await run_traversal_subagent(
            question=question,
            person_id=person_id,
            max_generations=max_generations,
            provider=self.provider,
            model=self.model,
            parent_ctx=parent_ctx,
        )


async def run_traversal_subagent(  # noqa: PLR0912, PLR0915  the trace recorder is naturally branchy
    *,
    question: str,
    person_id: UUID,
    max_generations: int,
    provider: LLMProvider,
    model: str,
    parent_ctx: ToolContext,
) -> TraversalSubagentResult:
    """Run the traversal subagent to completion and return its summary plus
    the proof-of-work trace.

    The inner host inherits the parent's session factory and tree id, but its
    capabilities collapse to `Capability.READ` and `traverse_and_summarize` is
    excluded from the catalog so the subagent cannot recurse into itself.

    Each inner event is forwarded to the active `SubagentEventSink` (if any)
    so the parent loop can stream the trace live to the UI. The same events
    are folded into a consolidated `trace` list on the result: contiguous
    `text_delta` and `thinking_delta` fragments coalesce into single text or
    thinking entries; `tool_use_started` opens a new tool entry that is then
    locked by `tool_use_finished` (input) and `tool_result` (output)."""
    sink = get_subagent_event_sink()
    sub_ctx = replace(
        parent_ctx,
        capabilities=Capability.READ,
        actor="agent.traversal",
        subagent_runner=None,
    )
    sub_host = ToolHost(
        get_registry(),
        context=sub_ctx,
        excluded_tools=frozenset({"traverse_and_summarize"}),
    )
    agent = ChatAgent(
        provider=provider,
        model=model,
        host=sub_host,
        system_prompt=TRAVERSAL_SUBAGENT_SYSTEM_PROMPT,
        budgets=Budgets(tokens=300_000, tool_calls=25, wall_clock_s=120),
    )
    initial = Message(
        role="user",
        content=[
            TextBlock(
                type="text",
                text=(
                    f"Anchor person id: {person_id}\n"
                    f"Maximum generations: {max_generations}\n\n"
                    f"Question: {question}"
                ),
            ),
        ],
    )
    log.info(
        "traversal_subagent.start",
        anchor_person_id=str(person_id),
        max_generations=max_generations,
        question=question[:200],
    )
    text_parts: list[str] = []
    persons: dict[UUID, PersonSummary] = {}
    trace: list[dict[str, Any]] = []
    open_tools: dict[str, int] = {}
    tokens_used = 0
    tool_calls_used = 0

    def _emit(payload: dict[str, Any]) -> None:
        if sink is not None:
            sink.emit(payload)

    async for event in agent.run_turn([initial]):
        if event.type == "text_delta":
            text = str(event.payload.get("text") or "")
            if not text:
                continue
            _emit({"type": "text_delta", "text": text})
            text_parts.append(text)
            if trace and trace[-1].get("type") == "text":
                trace[-1]["text"] += text
            else:
                trace.append({"type": "text", "text": text})
        elif event.type == "thinking_delta":
            text = str(event.payload.get("text") or "")
            if not text:
                continue
            _emit({"type": "thinking_delta", "text": text})
            last = trace[-1] if trace else None
            if last is not None and last.get("type") == "thinking" and not last.get("sealed"):
                last["text"] += text
            else:
                trace.append({"type": "thinking", "text": text})
        elif event.type == "thinking_break":
            # Boundary between two reasoning summary parts. Forward so the
            # live subagent stream splits its blocks, and seal the current
            # consolidated entry so the next thinking delta opens a new one.
            _emit({"type": "thinking_break"})
            if trace and trace[-1].get("type") == "thinking":
                trace[-1]["sealed"] = True
        elif event.type == "tool_use_started":
            tid = str(event.payload.get("id") or "")
            name = str(event.payload.get("name") or "")
            _emit({"type": "tool_use_started", "id": tid, "name": name})
            entry: dict[str, Any] = {
                "type": "tool_use",
                "id": tid,
                "name": name,
                "input": None,
                "output": None,
                "is_error": False,
            }
            trace.append(entry)
            open_tools[tid] = len(trace) - 1
        elif event.type == "tool_use_finished":
            tid = str(event.payload.get("id") or "")
            input_payload = event.payload.get("input")
            tool_name = str(event.payload.get("name") or "")
            _emit(
                {
                    "type": "tool_use_finished",
                    "id": tid,
                    "name": tool_name,
                    "input": input_payload,
                }
            )
            idx = open_tools.get(tid)
            if idx is not None:
                trace[idx]["input"] = input_payload
                if tool_name:
                    trace[idx]["name"] = tool_name
        elif event.type == "tool_result":
            tid = str(event.payload.get("tool_use_id") or "")
            output = event.payload.get("output")
            is_error = bool(event.payload.get("is_error", False))
            _emit(
                {
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "output": output,
                    "is_error": is_error,
                }
            )
            idx = open_tools.pop(tid, None)
            if idx is not None:
                trace[idx]["output"] = output
                trace[idx]["is_error"] = is_error
            if isinstance(output, dict):
                _collect_persons(output, persons)
        elif event.type == "done":
            tokens_used = int(event.payload.get("tokens_used") or 0)
            tool_calls_used = int(event.payload.get("tool_calls_used") or 0)
        elif event.type == "error":
            message = str(event.payload.get("message") or "")
            _emit({"type": "error", "message": message})
            log.warning(
                "traversal_subagent.error",
                anchor_person_id=str(person_id),
                error=message,
            )
            return TraversalSubagentResult(
                summary=message,
                persons=list(persons.values()),
                trace=trace,
                tokens_used=tokens_used,
                tool_calls_used=tool_calls_used,
            )
    log.info(
        "traversal_subagent.end",
        anchor_person_id=str(person_id),
        persons=len(persons),
        trace_items=len(trace),
        tokens_used=tokens_used,
        tool_calls_used=tool_calls_used,
    )
    return TraversalSubagentResult(
        summary="".join(text_parts).strip(),
        persons=list(persons.values()),
        trace=trace,
        tokens_used=tokens_used,
        tool_calls_used=tool_calls_used,
    )


def _collect_persons(output: dict[str, Any], persons: dict[UUID, PersonSummary]) -> None:
    """Walk a JSON-serialized tool result looking for `PersonSummary` shapes
    so the subagent can return a structured node list alongside its prose
    summary. Accepts the flat `results: [...]` shape used by `person_search`
    and `person_relations`, the nested `nodes[i].person` shape from
    `person_traverse`, and a single-person payload from `person_get`."""
    candidates: list[dict[str, Any]] = []
    results = output.get("results")
    if isinstance(results, list):
        candidates.extend(r for r in results if isinstance(r, dict))
    nodes = output.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                inner = node.get("person")
                if isinstance(inner, dict):
                    candidates.append(inner)
    if all(k in output for k in ("id", "display_name", "sex", "birth", "death")):
        candidates.append(output)
    for cand in candidates:
        try:
            summary = PersonSummary.model_validate(cand)
        except ValidationError:
            # A non-summary dict slipped past the shape probe (e.g. a search
            # result row from a tool we did not anticipate); ignore it rather
            # than corrupting the parent's structured node list.
            continue
        persons.setdefault(summary.id, summary)
