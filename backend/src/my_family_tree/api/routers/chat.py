"""Chat endpoint. v1 returns a non-streaming response; SSE streaming is wired
in once the frontend chat UI lands."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from my_family_tree.api.deps import LLMDep, SessionDep
from my_family_tree.llm.base import Message, ReasoningConfig, TextBlock

router = APIRouter()


class ChatTurn(BaseModel):
    """One historical exchange. The frontend keeps the conversation in local
    state and replays it on each request so the LLM sees prior context."""

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


_SYSTEM = (
    "You are the research assistant for My Family Tree, a personal genealogy "
    "workbench. Be concise. Format with Markdown when it helps "
    "(headings, bullets, tables, code blocks). Cite sources when you have them."
)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, llm: LLMDep, session: SessionDep) -> ChatResponse:
    """Non-streaming chat endpoint. Accepts the full conversation history so
    each turn has prior context. The streaming SSE variant is the next iteration."""
    del session  # unused in v1 stub
    provider, model = llm.resolve()

    messages: list[Message] = []
    for turn in req.history:
        messages.append(
            Message(role=turn.role, content=[TextBlock(type="text", text=turn.content)])
        )
    messages.append(Message(role="user", content=[TextBlock(type="text", text=req.message)]))

    result = await provider.complete(
        model=model,
        system=_SYSTEM,
        messages=messages,
        max_tokens=2048,
        reasoning=ReasoningConfig(effort="medium"),
    )
    text = "".join(b.text for b in result.blocks if isinstance(b, TextBlock))
    return ChatResponse(
        text=text,
        model=result.model,
        provider=result.provider,
        usage={
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "reasoning_tokens": result.usage.reasoning_tokens,
        },
    )
