"""Chat endpoints. The frontend uses `/chat/stream` (SSE) for the live UI;
`/chat` returns a single JSON blob for scripts and tests. Both run the same
`ChatAgent` with the in-process `ToolHost`, so the LLM has access to the
full MCP tool catalog and can propose persistent records.

Both endpoints bootstrap a `Conversation` row (when the client doesn't pass
one) and an `AgentRun` row for the turn. The agent_run_id is carried into
the `ToolContext` so every proposal the agent emits is linked back to the
chat turn that produced it. At approve time, the applier reads
`agent_run.conversation_id` to dedup the synthetic chat `Source` per
conversation rather than collapsing every turn onto one row."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from my_family_tree.agent.budgets import Budgets
from my_family_tree.agent.loop import ChatAgent, ChatTurnEvent
from my_family_tree.api.deps import LLMDep, SettingsDep
from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.db.session import session_scope
from my_family_tree.llm.base import Message, TextBlock
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
from my_family_tree.models.enums import AgentRole, RunStatus
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
    turn. Returns the resolved `(conversation_id, agent_run_id)`.

    The conversation is the durable thread the user sees; the agent run is the
    per-turn record that proposals link to so provenance writes can find their
    originating thread at apply time."""
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


def _build_messages(req: ChatRequest) -> list[Message]:
    messages: list[Message] = []
    for turn in req.history:
        messages.append(
            Message(role=turn.role, content=[TextBlock(type="text", text=turn.content)])
        )
    messages.append(Message(role="user", content=[TextBlock(type="text", text=req.message)]))
    return messages


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
    settings: SettingsDep,
    request: Request,
) -> ChatResponse:
    """Non-streaming chat. Drains the agent's event stream into a single JSON
    response. Used by tests and scripts; the frontend uses `/chat/stream`."""
    del settings
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
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    proposal_ids: list[UUID] = []
    usage: dict[str, Any] = {}
    tokens_used = 0
    tool_calls_used = 0
    error_message: str | None = None

    async for evt in agent.run_turn(_build_messages(req)):
        if evt.type == "text_delta":
            text_parts.append(evt.payload.get("text", ""))
        elif evt.type == "tool_use_finished":
            tool_calls.append({"id": evt.payload.get("id"), "name": evt.payload.get("name")})
        elif evt.type == "tool_result":
            for call in tool_calls:
                if call["id"] == evt.payload.get("tool_use_id"):
                    call["output"] = evt.payload.get("output")
                    call["is_error"] = evt.payload.get("is_error", False)
                    break
        elif evt.type == "usage":
            usage = evt.payload
        elif evt.type == "done":
            usage = evt.payload.get("usage", usage) or usage
            proposal_ids = [UUID(pid) for pid in evt.payload.get("proposal_ids", [])]
            tokens_used = int(evt.payload.get("tokens_used", 0))
            tool_calls_used = int(evt.payload.get("tool_calls_used", 0))
        elif evt.type == "error":
            error_message = str(evt.payload.get("message", ""))
            log.warning("chat.agent_error", message=error_message)

    await _finalize_run(
        request,
        agent_run_id=agent_run_id,
        status=RunStatus.failed if error_message else RunStatus.completed,
        error=error_message,
        tokens_used=tokens_used,
        tool_calls_used=tool_calls_used,
    )

    return ChatResponse(
        text="".join(text_parts),
        model=agent.model,
        provider=agent.provider.name,
        conversation_id=conversation_id,
        agent_run_id=agent_run_id,
        usage=usage,
        proposal_ids=proposal_ids,
        tool_calls=tool_calls,
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    llm: LLMDep,
    settings: SettingsDep,
    request: Request,
) -> EventSourceResponse:
    """Streaming chat. Returns an SSE stream of agent events. Each event has
    `event: <type>` and `data: <json>`."""
    del settings
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
        tokens_used = 0
        tool_calls_used = 0
        error_message: str | None = None
        try:
            async for evt in agent.run_turn(_build_messages(req)):
                if evt.type == "done":
                    tokens_used = int(evt.payload.get("tokens_used", 0))
                    tool_calls_used = int(evt.payload.get("tool_calls_used", 0))
                elif evt.type == "error":
                    error_message = str(evt.payload.get("message", ""))
                yield _sse(evt.type, _augment(evt))
        except Exception as e:  # pragma: no cover  defensive
            log.exception("chat.stream_unhandled")
            error_message = str(e)
            yield _sse("error", {"message": str(e)})
        finally:
            await _finalize_run(
                request,
                agent_run_id=agent_run_id,
                status=RunStatus.failed if error_message else RunStatus.completed,
                error=error_message,
                tokens_used=tokens_used,
                tool_calls_used=tool_calls_used,
            )

    return EventSourceResponse(event_stream())


def _sse(event_type: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event_type, "data": json.dumps(data, default=str)}


def _augment(evt: ChatTurnEvent) -> dict[str, Any]:
    return dict(evt.payload)
