"""Message aggregate.

`content_json` is a provider-neutral list of content blocks shaped like:
- {type: "text", text: "..."}
- {type: "tool_use", id: "...", name: "...", input: {...}}
- {type: "tool_result", tool_use_id: "...", output: {...}, is_error: false}
- {type: "thinking", summary: "...", tokens: 1234}    # never raw reasoning text
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from my_family_tree.db.types import PgUUID
from my_family_tree.models._columns import (
    created_at_column,
    enum_column,
    fk_column,
    int_column,
    jsonb_column,
    pk_column,
    text_column,
)
from my_family_tree.models.enums import MessageRole


class Message(SQLModel, table=True):
    __tablename__ = "message"

    id: UUID = pk_column()
    conversation_id: UUID = fk_column("conversation.id", ondelete="CASCADE")
    role: MessageRole = enum_column(MessageRole, "message_role", nullable=False, index=True)

    content_json: list[dict] = jsonb_column(nullable=False, default=list)

    model: str | None = text_column()
    provider: str | None = text_column()
    input_tokens: int | None = int_column()
    output_tokens: int | None = int_column()
    cached_input_tokens: int | None = int_column()
    reasoning_tokens: int | None = int_column()

    tool_call_id: str | None = text_column()
    parent_message_id: UUID | None = Field(
        default=None,
        sa_column=Column(PgUUID(), nullable=True, index=True),
    )

    created_at: datetime = created_at_column()
