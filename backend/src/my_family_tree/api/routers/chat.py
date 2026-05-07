"""Chat endpoints. The frontend uses `/chat/stream` (SSE) for the live UI;
`/chat` returns a single JSON blob for scripts and tests. Both run the same
`ChatAgent` with the in-process `ToolHost`, so the LLM has access to the
full MCP tool catalog and can propose persistent records."""

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
    usage: dict[str, Any]
    proposal_ids: list[UUID] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


def _agent_for_request(req: ChatRequest, request: Request, llm: Any) -> ChatAgent:
    """Build a ChatAgent bound to this request's session factory and tree."""
    session_factory = request.app.state.session_factory
    ctx = ToolContext(
        session_factory=session_factory,
        tree_id=req.tree_id,
        capabilities=Capability.chat_default(),
        actor="agent",
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
    agent = _agent_for_request(req, request, llm)
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    proposal_ids: list[UUID] = []
    usage: dict[str, Any] = {}

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
        elif evt.type == "error":
            log.warning("chat.agent_error", message=evt.payload.get("message"))

    return ChatResponse(
        text="".join(text_parts),
        model=agent.model,
        provider=agent.provider.name,
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
    agent = _agent_for_request(req, request, llm)

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        yield _sse(
            "start", {"conversation_id": str(req.conversation_id) if req.conversation_id else None}
        )
        try:
            async for evt in agent.run_turn(_build_messages(req)):
                yield _sse(evt.type, _augment(evt))
        except Exception as e:  # pragma: no cover  defensive
            log.exception("chat.stream_unhandled")
            yield _sse("error", {"message": str(e)})

    return EventSourceResponse(event_stream())


def _sse(event_type: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event_type, "data": json.dumps(data, default=str)}


def _augment(evt: ChatTurnEvent) -> dict[str, Any]:
    return dict(evt.payload)
