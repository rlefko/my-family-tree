"""Chat endpoint. v1 returns a non-streaming response; SSE streaming is wired
in once the frontend chat UI lands."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from my_family_tree.api.deps import LLMDep, SessionDep
from my_family_tree.llm.base import Message, ReasoningConfig, TextBlock

router = APIRouter()


class ChatRequest(BaseModel):
    tree_id: UUID
    message: str
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    text: str
    model: str
    provider: str
    usage: dict[str, Any]


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, llm: LLMDep, session: SessionDep) -> ChatResponse:
    """Non-streaming v1 chat endpoint. The streaming variant (SSE) is added
    when the frontend chat UI is wired up."""
    del session  # unused in v1 stub
    provider, model = llm.resolve()
    result = await provider.complete(
        model=model,
        system="You are a helpful research assistant.",
        messages=[Message(role="user", content=[TextBlock(type="text", text=req.message)])],
        max_tokens=1024,
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
