"""Conversation endpoints. The chat UI uses these to list prior threads
and rehydrate the active thread on page reload. Each conversation aggregates
the user/assistant Message rows the chat router persists per turn."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from my_family_tree.api.deps import SessionDep
from my_family_tree.core.errors import NotFoundError
from my_family_tree.models.conversation import Conversation
from my_family_tree.models.message import Message
from my_family_tree.models.proposal import Proposal

router = APIRouter()


class ConversationRow(BaseModel):
    id: UUID
    title: str | None = None
    last_message_at: datetime | None = None
    created_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationRow]


class MessageRow(BaseModel):
    id: UUID
    role: str
    content: list[dict[str, Any]]
    created_at: datetime
    input_tokens: int | None = None
    output_tokens: int | None = None
    proposal_ids: list[UUID] = []


class ConversationDetail(BaseModel):
    id: UUID
    title: str | None
    last_message_at: datetime | None
    messages: list[MessageRow]


@router.get("/conversations", response_model=ConversationList)
async def list_conversations(session: SessionDep, limit: int = 50) -> ConversationList:
    stmt = (
        select(Conversation)
        .where(Conversation.deleted_at.is_(None))
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return ConversationList(
        items=[
            ConversationRow(
                id=c.id,
                title=c.title,
                last_message_at=c.last_message_at,
                created_at=c.created_at,
            )
            for c in rows
        ]
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: UUID, session: SessionDep) -> ConversationDetail:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.deleted_at is not None:
        raise NotFoundError(f"conversation {conversation_id} not found")

    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = list((await session.execute(msg_stmt)).scalars().all())
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        last_message_at=conv.last_message_at,
        messages=[
            MessageRow(
                id=m.id,
                role=m.role.value,
                content=m.content_json or [],
                created_at=m.created_at,
                input_tokens=m.input_tokens,
                output_tokens=m.output_tokens,
                proposal_ids=_proposal_ids_in_message(m),
            )
            for m in messages
        ],
    )


def _proposal_ids_in_message(m: Message) -> list[UUID]:
    """Pull proposal ids out of the assistant message's content_json. We append
    a `{type: 'proposals_summary', proposal_ids: [...]}` block whenever the
    turn produced any."""
    out: list[UUID] = []
    for block in m.content_json or []:
        if isinstance(block, dict) and block.get("type") == "proposals_summary":
            for pid in block.get("proposal_ids", []) or []:
                try:
                    out.append(UUID(str(pid)))
                except ValueError:
                    continue
    return out


# Used by the chat router to also surface proposal status when rehydrating.
async def proposals_for_ids(session: SessionDep, ids: list[UUID]) -> list[Proposal]:
    if not ids:
        return []
    stmt = select(Proposal).where(Proposal.id.in_(ids))
    return list((await session.execute(stmt)).scalars().all())
