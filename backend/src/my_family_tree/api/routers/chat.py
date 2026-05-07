"""Chat endpoints. `/chat/stream` (SSE) drives the UI; `/chat` returns one
JSON blob for scripts and tests. Both run `ChatAgent` with the in-process
`ToolHost`; proposals link back to chat via `agent_run_id`."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from my_family_tree.agent.budgets import Budgets
from my_family_tree.agent.loop import ChatAgent, ChatTurnEvent
from my_family_tree.api.deps import LLMDep
from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.db.session import session_scope
from my_family_tree.llm.base import Message as LLMMessage, TextBlock
from my_family_tree.mcp.host import ToolContext, ToolHost
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.mcp.tools import (  # noqa: F401  ensure side-effect imports happen
    chunks,
    claims,
    conflicts,
    documents,
    events,
    input,
    persons,
    places,
    relationships,
    sources,
    stats,
)
from my_family_tree.models.agent_run import AgentRun
from my_family_tree.models.conversation import Conversation
from my_family_tree.models.enums import AgentRole, MessageRole, RunStatus
from my_family_tree.models.message import Message
from my_family_tree.models.tree import Tree

DEFAULT_TREE_NAME = "My Family Tree"

log = get_logger(__name__)

router = APIRouter()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    tree_id: UUID
    message: str
    history: list[ChatTurn] = Field(default_factory=list)
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    text: str
    model: str
    provider: str
    conversation_id: UUID
    agent_run_id: UUID
    usage: dict[str, Any]
    proposal_ids: list[UUID] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


@dataclass
class _TurnAggregator:
    """Collects agent events into a single `(text, tool_calls, proposal_ids,
    usage)` snapshot we can persist on stream end."""

    text_parts: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    proposal_ids: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    tool_calls_used: int = 0
    error_message: str | None = None

    def consume(self, evt: ChatTurnEvent) -> None:  # noqa: PLR0912  one branch per event type
        if evt.type == "text_delta":
            self.text_parts.append(str(evt.payload.get("text") or ""))
        elif evt.type == "tool_use_started":
            self.tool_calls.append(
                {
                    "type": "tool_use",
                    "id": str(evt.payload.get("id") or ""),
                    "name": str(evt.payload.get("name") or ""),
                    "input": None,
                    "output": None,
                    "is_error": False,
                }
            )
        elif evt.type == "tool_use_finished":
            tid = str(evt.payload.get("id") or "")
            for call in self.tool_calls:
                if call["id"] == tid:
                    if "input" in evt.payload:
                        call["input"] = evt.payload.get("input")
                    if "name" in evt.payload and not call.get("name"):
                        call["name"] = str(evt.payload.get("name") or "")
                    break
        elif evt.type == "tool_result":
            tid = str(evt.payload.get("tool_use_id") or "")
            for call in self.tool_calls:
                if call["id"] == tid:
                    call["output"] = evt.payload.get("output")
                    call["is_error"] = bool(evt.payload.get("is_error", False))
                    break
        elif evt.type == "usage":
            self.usage = dict(evt.payload)
        elif evt.type == "done":
            self.usage = evt.payload.get("usage", self.usage) or self.usage
            self.proposal_ids = [str(pid) for pid in evt.payload.get("proposal_ids", []) or []]
            self.tokens_used = int(evt.payload.get("tokens_used", 0) or 0)
            self.tool_calls_used = int(evt.payload.get("tool_calls_used", 0) or 0)
        elif evt.type == "error":
            self.error_message = str(evt.payload.get("message") or "")

    def assistant_content_json(self) -> list[dict[str, Any]]:
        """Build the saved content_json for the assistant Message. Tool calls
        come first (in the order they happened), then the final text, then a
        `proposals_summary` block when proposals were queued. The frontend
        rehydrator reverses this to repopulate the bubble."""
        blocks: list[dict[str, Any]] = list(self.tool_calls)
        text = "".join(self.text_parts)
        if text:
            blocks.append({"type": "text", "text": text})
        if self.proposal_ids:
            blocks.append({"type": "proposals_summary", "proposal_ids": self.proposal_ids})
        return blocks


async def _ensure_conversation_and_run(
    request: Request,
    *,
    tree_id: UUID,
    conversation_id: UUID | None,
    goal: str,
    model: str,
    provider: str,
) -> tuple[UUID, UUID]:
    """Materialize a `Conversation` (if absent) and an `AgentRun` for this
    turn. Returns the resolved `(conversation_id, agent_run_id)`."""
    session_factory = request.app.state.session_factory
    async with session_scope(session_factory) as session:
        tree = await session.get(Tree, tree_id)
        if tree is None:
            tree = Tree(id=tree_id, name=DEFAULT_TREE_NAME)
            session.add(tree)
            await session.flush()

        if conversation_id is None:
            conv = Conversation(tree_id=tree_id)
            session.add(conv)
            await session.flush()
            conversation_id = conv.id
        else:
            conv = await session.get(Conversation, conversation_id)
            if conv is None:
                conv = Conversation(id=conversation_id, tree_id=tree_id)
                session.add(conv)
                await session.flush()
        conv.last_message_at = utcnow()
        if conv.title is None and goal:
            conv.title = goal[:80]

        run = AgentRun(
            conversation_id=conversation_id,
            role=AgentRole.chat,
            goal=goal[:500],
            status=RunStatus.running,
            model=model,
            provider=provider,
            started_at=utcnow(),
        )
        session.add(run)
        await session.flush()
        return conversation_id, run.id


def _agent_for_request(
    req: ChatRequest,
    request: Request,
    llm: Any,
    *,
    agent_run_id: UUID,
) -> ChatAgent:
    """Build a ChatAgent bound to this request's session factory and tree."""
    session_factory = request.app.state.session_factory
    ctx = ToolContext(
        session_factory=session_factory,
        tree_id=req.tree_id,
        capabilities=Capability.chat_default(),
        actor="agent",
        agent_run_id=agent_run_id,
    )
    host = ToolHost(get_registry(), context=ctx)
    provider, model = llm.resolve()
    return ChatAgent(
        provider=provider,
        model=model,
        host=host,
        budgets=Budgets(),
    )


def _build_messages(req: ChatRequest) -> list[LLMMessage]:
    messages: list[LLMMessage] = []
    for turn in req.history:
        messages.append(
            LLMMessage(role=turn.role, content=[TextBlock(type="text", text=turn.content)])
        )
    messages.append(LLMMessage(role="user", content=[TextBlock(type="text", text=req.message)]))
    return messages


async def _persist_turn(
    request: Request,
    *,
    conversation_id: UUID,
    user_text: str,
    aggregator: _TurnAggregator,
    model: str,
    provider: str,
) -> None:
    """Write the user prompt and the assistant response as `Message` rows.
    Called from the SSE `finally` block and from the JSON `/chat` handler so
    both paths produce the same persistent record."""
    session_factory = request.app.state.session_factory
    async with session_scope(session_factory) as session:
        user_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.user,
            content_json=[{"type": "text", "text": user_text}],
        )
        session.add(user_msg)
        await session.flush()

        usage = aggregator.usage or {}
        assistant_msg = Message(
            conversation_id=conversation_id,
            role=MessageRole.assistant,
            content_json=aggregator.assistant_content_json(),
            model=model,
            provider=provider,
            input_tokens=int(usage.get("input_tokens") or 0) or None,
            output_tokens=int(usage.get("output_tokens") or 0) or None,
            cached_input_tokens=int(usage.get("cached_input_tokens") or 0) or None,
            reasoning_tokens=int(usage.get("reasoning_tokens") or 0) or None,
            parent_message_id=user_msg.id,
        )
        session.add(assistant_msg)
        await session.flush()


async def _finalize_run(
    request: Request,
    *,
    agent_run_id: UUID,
    status: RunStatus,
    error: str | None = None,
    tokens_used: int = 0,
    tool_calls_used: int = 0,
) -> None:
    """Mark the `AgentRun` finished with the final status and bookkeeping."""
    session_factory = request.app.state.session_factory
    async with session_scope(session_factory) as session:
        run = await session.get(AgentRun, agent_run_id)
        if run is None:
            return
        run.status = status
        run.ended_at = utcnow()
        run.tokens_used = tokens_used
        run.tool_calls_used = tool_calls_used
        if error is not None:
            run.error = error[:2000]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    llm: LLMDep,
    request: Request,
) -> ChatResponse:
    """Non-streaming chat. Drains the agent's event stream into a single JSON
    response. Used by tests and scripts; the frontend uses `/chat/stream`."""
    provider, model = llm.resolve()
    conversation_id, agent_run_id = await _ensure_conversation_and_run(
        request,
        tree_id=req.tree_id,
        conversation_id=req.conversation_id,
        goal=req.message,
        model=model,
        provider=provider.name,
    )
    agent = _agent_for_request(req, request, llm, agent_run_id=agent_run_id)
    aggregator = _TurnAggregator()

    async for evt in agent.run_turn(_build_messages(req)):
        aggregator.consume(evt)
        if evt.type == "error":
            log.warning("chat.agent_error", message=aggregator.error_message)

    await _persist_turn(
        request,
        conversation_id=conversation_id,
        user_text=req.message,
        aggregator=aggregator,
        model=agent.model,
        provider=agent.provider.name,
    )
    await _finalize_run(
        request,
        agent_run_id=agent_run_id,
        status=RunStatus.failed if aggregator.error_message else RunStatus.completed,
        error=aggregator.error_message,
        tokens_used=aggregator.tokens_used,
        tool_calls_used=aggregator.tool_calls_used,
    )

    return ChatResponse(
        text="".join(aggregator.text_parts),
        model=agent.model,
        provider=agent.provider.name,
        conversation_id=conversation_id,
        agent_run_id=agent_run_id,
        usage=aggregator.usage,
        proposal_ids=[UUID(pid) for pid in aggregator.proposal_ids],
        tool_calls=[
            {"id": c["id"], "name": c["name"], "input": c.get("input"), "output": c.get("output")}
            for c in aggregator.tool_calls
        ],
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    llm: LLMDep,
    request: Request,
) -> EventSourceResponse:
    """Streaming chat. Returns an SSE stream of agent events. Each event has
    `event: <type>` and `data: <json>`."""
    provider, model = llm.resolve()
    conversation_id, agent_run_id = await _ensure_conversation_and_run(
        request,
        tree_id=req.tree_id,
        conversation_id=req.conversation_id,
        goal=req.message,
        model=model,
        provider=provider.name,
    )
    agent = _agent_for_request(req, request, llm, agent_run_id=agent_run_id)

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        yield _sse(
            "start",
            {
                "conversation_id": str(conversation_id),
                "agent_run_id": str(agent_run_id),
            },
        )
        aggregator = _TurnAggregator()
        try:
            async for evt in agent.run_turn(_build_messages(req)):
                aggregator.consume(evt)
                yield _sse(evt.type, _augment(evt))
        except Exception as e:  # pragma: no cover  defensive
            log.exception("chat.stream_unhandled")
            aggregator.error_message = str(e)
            yield _sse("error", {"message": str(e)})
        finally:
            await _persist_turn(
                request,
                conversation_id=conversation_id,
                user_text=req.message,
                aggregator=aggregator,
                model=agent.model,
                provider=agent.provider.name,
            )
            await _finalize_run(
                request,
                agent_run_id=agent_run_id,
                status=RunStatus.failed if aggregator.error_message else RunStatus.completed,
                error=aggregator.error_message,
                tokens_used=aggregator.tokens_used,
                tool_calls_used=aggregator.tool_calls_used,
            )

    return EventSourceResponse(event_stream())


def _sse(event_type: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event_type, "data": json.dumps(data, default=str)}


def _augment(evt: ChatTurnEvent) -> dict[str, Any]:
    return dict(evt.payload)
