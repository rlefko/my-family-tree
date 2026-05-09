"""Chat endpoints. `/chat/stream` (SSE) drives the UI; `/chat` returns one
JSON blob for scripts and tests. Both run `ChatAgent` with the in-process
`ToolHost`; proposals link back to chat via `agent_run_id`."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from my_family_tree.agent.budgets import Budgets
from my_family_tree.agent.loop import ChatAgent, ChatTurnEvent
from my_family_tree.agent.traversal_subagent import TraversalSubagentRunner
from my_family_tree.api.deps import LLMDep
from my_family_tree.core.config import get_settings
from my_family_tree.core.errors import StorageError
from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.db.session import session_scope
from my_family_tree.llm.base import (
    ContentBlock,
    ImageBlock,
    Message as LLMMessage,
    ReasoningConfig,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from my_family_tree.mcp import tools  # noqa: F401  importing the package registers every tool
from my_family_tree.mcp.host import ToolContext, ToolHost
from my_family_tree.mcp.registry import Capability, get_registry
from my_family_tree.models.agent_run import AgentRun
from my_family_tree.models.conversation import Conversation
from my_family_tree.models.document import Document
from my_family_tree.models.enums import (
    AgentRole,
    DocumentKind,
    MessageRole,
    ProposalAction,
    ProposalStatus,
    RunStatus,
    SubjectType,
)
from my_family_tree.models.message import Message
from my_family_tree.models.proposal import Proposal
from my_family_tree.models.tree import Tree

DEFAULT_TREE_NAME = "My Family Tree"

log = get_logger(__name__)

router = APIRouter()


class ChatAttachmentInput(BaseModel):
    document_id: UUID


class ChatRequest(BaseModel):
    tree_id: UUID
    message: str
    attachments: list[ChatAttachmentInput] = Field(default_factory=list)
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
    """Build a ChatAgent bound to this request's session factory and tree.
    Optional external services (`web_search`, `genealogy`, `external_ingest`)
    are pulled from app state and threaded through both the `ToolContext`
    (so handlers can call them) and the `ToolHost` (so the catalog hides
    tools whose providers are unconfigured). The `subagent_runner` lets
    `traverse_and_summarize` spawn a read-only inner agent without exposing
    the LLM provider to leaf tools."""
    state = request.app.state
    session_factory = state.session_factory
    provider, model = llm.resolve()
    ctx = ToolContext(
        session_factory=session_factory,
        tree_id=req.tree_id,
        capabilities=Capability.chat_default(),
        actor="agent",
        agent_run_id=agent_run_id,
        storage=getattr(state, "storage", None),
        embeddings=getattr(state, "embeddings_client", None),
        web_search=getattr(state, "web_search", None),
        genealogy=getattr(state, "genealogy", None),
        external_ingest=getattr(state, "external_ingest", None),
        subagent_runner=TraversalSubagentRunner(provider=provider, model=model),
    )
    host = ToolHost(get_registry(), context=ctx, settings=get_settings())
    # Chat-facing latency trim. The traversal subagent intentionally keeps
    # the thorough ChatAgent defaults so deep walks stay deliberate.
    return ChatAgent(
        provider=provider,
        model=model,
        host=host,
        budgets=Budgets(),
        reasoning=ReasoningConfig(effort="low"),
        max_output_tokens=12288,
    )


@dataclass(slots=True)
class _AttachmentRef:
    document_id: UUID
    filename: str | None
    kind: str | None
    mime_type: str | None


@dataclass(slots=True)
class _ResolvedAttachment:
    ref: _AttachmentRef
    image: ImageBlock | None


async def _resolve_attachments(
    request: Request,
    document_ids: list[UUID],
    *,
    inline_budget: int,
) -> tuple[list[_ResolvedAttachment], int]:
    """Look up each document and, for image attachments, fetch and base64-
    encode the bytes (subject to `inline_budget`). Documents that no longer
    exist or whose bytes are unavailable are returned with `image=None` so
    the caller can still emit a text reference for the agent to follow up via
    `hybrid_search`. Returns (resolved_list_in_input_order, remaining_budget).
    """
    if not document_ids:
        return [], inline_budget

    session_factory = request.app.state.session_factory
    storage = request.app.state.storage

    docs_by_id: dict[UUID, Document] = {}
    async with session_scope(session_factory) as session:
        rows = (
            (await session.execute(select(Document).where(Document.id.in_(document_ids))))
            .scalars()
            .all()
        )
        for d in rows:
            docs_by_id[d.id] = d

    # Decide which docs to inline; cap to the budget. Walk the input order
    # so the most recently appended attachments (typical "I just attached
    # this" intent) get priority.
    image_doc_ids: list[UUID] = []
    for did in document_ids:
        doc = docs_by_id.get(did)
        if doc is None:
            continue
        if doc.mime_type.startswith("image/") or doc.kind == DocumentKind.image:
            image_doc_ids.append(did)

    inline_targets = image_doc_ids[:inline_budget]

    async def _fetch(did: UUID) -> tuple[UUID, bytes | None]:
        doc = docs_by_id.get(did)
        if doc is None:
            return did, None
        try:
            data = await storage.get(doc.storage_key)
        except StorageError as e:
            log.warning("chat.image_fetch_failed", document_id=str(did), error=str(e))
            return did, None
        return did, data

    fetched: dict[UUID, bytes] = {}
    if inline_targets:
        results = await asyncio.gather(*[_fetch(d) for d in inline_targets])
        for did, data in results:
            if data is not None:
                fetched[did] = data

    out: list[_ResolvedAttachment] = []
    used = 0
    for did in document_ids:
        doc = docs_by_id.get(did)
        ref = _AttachmentRef(
            document_id=did,
            filename=(doc.original_filename if doc is not None else None),
            kind=(doc.kind.value if doc is not None else None),
            mime_type=(doc.mime_type if doc is not None else None),
        )
        image: ImageBlock | None = None
        if did in fetched and doc is not None:
            image = ImageBlock(
                type="image",
                media_type=doc.mime_type or "image/png",
                data_b64=base64.b64encode(fetched[did]).decode("ascii"),
            )
            used += 1
        out.append(_ResolvedAttachment(ref=ref, image=image))

    return out, max(inline_budget - used, 0)


def _attachment_suffix(refs: list[_AttachmentRef]) -> str:
    """Build the `[Attached: ...]` suffix the agent watches for. Lists each
    attachment's filename, kind, and document id so the agent can scope a
    follow-up `hybrid_search`."""
    if not refs:
        return ""
    parts: list[str] = []
    for r in refs:
        name = r.filename or "document"
        kind = r.kind or "unknown"
        parts.append(f"{name} ({kind}, id: {r.document_id})")
    return "[Attached: " + ", ".join(parts) + "]"


def _content_blocks_for_user_turn(
    text: str,
    resolved: list[_ResolvedAttachment],
) -> list[ContentBlock]:
    """Combine the user's text with the bracket suffix and any inline image
    blocks. Image blocks come last so the model treats them as evidence the
    text is about to discuss."""
    refs = [r.ref for r in resolved]
    suffix = _attachment_suffix(refs)
    text_with_suffix = text
    if suffix:
        text_with_suffix = (text + "\n\n" + suffix) if text else suffix

    blocks: list[ContentBlock] = []
    if text_with_suffix:
        blocks.append(TextBlock(type="text", text=text_with_suffix))
    for r in resolved:
        if r.image is not None:
            blocks.append(r.image)
    return blocks


def _user_attachment_doc_ids(content_json: list[dict[str, Any]]) -> list[UUID]:
    """Pull `document_id`s out of attachment blocks on a persisted user
    message, preserving order."""
    out: list[UUID] = []
    for block in content_json or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "attachment":
            continue
        try:
            out.append(UUID(str(block.get("document_id"))))
        except ValueError, TypeError:
            continue
    return out


def _text_from_blocks(content_json: list[dict[str, Any]]) -> str:
    """Concatenate `text` blocks from a persisted message's `content_json`.

    Used for user rows, which may also carry `attachment` blocks resolved
    separately. Assistant rows go through `_assistant_messages_from_content`
    so prior tool calls and their results are rehydrated for the LLM."""
    return "".join(
        str(b.get("text", ""))
        for b in (content_json or [])
        if isinstance(b, dict) and b.get("type") == "text"
    )


def _assistant_messages_from_content(
    content_json: list[dict[str, Any]],
) -> list[LLMMessage]:
    """Rehydrate a persisted assistant row into the (assistant, tool?) LLM
    message pair the providers expect, skipping `proposals_summary` and
    `thinking` blocks. A `tool_use` with no recorded `output` synthesizes
    an error `ToolResultBlock` so the tool_use to tool_result pairing the
    Anthropic and OpenAI APIs require is never violated."""
    text_parts: list[str] = []
    tool_uses: list[ToolUseBlock] = []
    tool_results: list[ToolResultBlock] = []
    for block in content_json or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text = str(block.get("text", ""))
            if text:
                text_parts.append(text)
        elif btype == "tool_use":
            call_id = str(block.get("id") or "")
            name = str(block.get("name") or "")
            raw_input = block.get("input")
            input_dict = raw_input if isinstance(raw_input, dict) else {}
            tool_uses.append(ToolUseBlock(type="tool_use", id=call_id, name=name, input=input_dict))
            output = block.get("output")
            is_error = bool(block.get("is_error", False))
            if output is None:
                output = {"error": "tool result missing from persisted turn"}
                is_error = True
            tool_results.append(
                ToolResultBlock(
                    type="tool_result",
                    tool_use_id=call_id,
                    output=output,
                    is_error=is_error,
                )
            )

    assistant_blocks: list[ContentBlock] = []
    if text_parts:
        assistant_blocks.append(TextBlock(type="text", text="".join(text_parts)))
    assistant_blocks.extend(tool_uses)

    out: list[LLMMessage] = []
    if assistant_blocks:
        out.append(LLMMessage(role="assistant", content=assistant_blocks))
    if tool_results:
        out.append(LLMMessage(role="tool", content=list(tool_results)))
    return out


@dataclass(slots=True, frozen=True)
class _ProposalRow:
    """Slim view of a `Proposal` used to render the [Session state] block."""

    proposal_id: UUID
    action: ProposalAction
    target_type: SubjectType | None
    payload: dict[str, Any]
    status: ProposalStatus
    target_id: UUID | None


_SESSION_STATE_HEADER = (
    "[Session state] Proposals created in this conversation. Treat "
    "status=approved as canonical: do NOT re-propose the same person, "
    "relationship, event, place, or source, and you may reference its "
    "target_id directly. Treat status=pending as already queued: do not "
    "duplicate it. Treat status=rejected as a decision not to retry "
    "unless the user asks explicitly. status=expired is stale. This "
    "block is out-of-band like [Attached: ...]; do not echo it back."
)


def _subject_update_fields(payload: dict[str, Any], pk: str) -> str:
    keys = sorted(k for k in payload if k != pk)
    return f"update fields: {', '.join(keys)}" if keys else "update"


# target_type=None covers source/claim/conflict proposals; mirrors the
# `_APPLY_ORDER` shape in `proposals.py`.
_SUBJECT_DISPATCH: dict[
    tuple[ProposalAction, SubjectType | None], Callable[[dict[str, Any]], str]
] = {
    (ProposalAction.create, SubjectType.person): lambda p: str(
        p.get("display_name") or "(unnamed person)"
    ),
    (ProposalAction.update, SubjectType.person): lambda p: _subject_update_fields(p, "person_id"),
    (ProposalAction.merge, SubjectType.person): lambda p: (
        f"merge loser {p.get('loser_id')} into winner {p.get('winner_id')}"
    ),
    (ProposalAction.create, SubjectType.relationship): lambda p: (
        f"{p.get('type') or 'relationship'}: {p.get('subject_id')} -> {p.get('object_id')}"
    ),
    (ProposalAction.delete, SubjectType.relationship): lambda p: (
        f"delete relationship {p.get('relationship_id')}"
    ),
    (ProposalAction.create, SubjectType.event): lambda p: (
        f"{p.get('type') or 'event'} {p.get('date_text') or ''}".strip()
    ),
    (ProposalAction.update, SubjectType.event): lambda p: _subject_update_fields(p, "event_id"),
    (ProposalAction.create, SubjectType.place): lambda p: str(p.get("name") or "(unnamed place)"),
    (ProposalAction.create, None): lambda p: str(p.get("title") or p.get("kind") or "source"),
    (ProposalAction.accept_claim, None): lambda p: f"accept claim {p.get('claim_id')}",
    (ProposalAction.reject_claim, None): lambda p: f"reject claim {p.get('claim_id')}",
    (ProposalAction.resolve_conflict, None): lambda p: f"resolve conflict {p.get('conflict_id')}",
}


def _proposal_subject(
    action: ProposalAction, target_type: SubjectType | None, payload: dict[str, Any]
) -> str:
    """One-line summary dispatched on `(action, target_type)`, falling back
    to a truncated JSON dump for shapes the dispatch table does not cover."""
    handler = _SUBJECT_DISPATCH.get((action, target_type))
    if handler is not None:
        return handler(payload)
    return json.dumps(payload, sort_keys=True, default=str)[:80]


def _format_session_state(rows: list[_ProposalRow]) -> str:
    """Render proposal rows into the [Session state] block, or '' when
    there is nothing to render so the caller can skip the injection."""
    if not rows:
        return ""
    lines: list[str] = [_SESSION_STATE_HEADER]
    for row in rows:
        subject = _proposal_subject(row.action, row.target_type, row.payload)
        target_type_str = row.target_type.value if row.target_type is not None else "-"
        target_str = (
            f" -> {row.target_type.value if row.target_type is not None else 'target'} "
            f"{row.target_id}"
            if row.target_id is not None
            else ""
        )
        lines.append(
            f"- proposal {row.proposal_id} | {row.action.value} {target_type_str} | "
            f"{subject} | status={row.status.value}{target_str}"
        )
    return "\n".join(lines)


async def _proposal_rows_for_conversation(
    request: Request,
    conversation_id: UUID,
) -> list[_ProposalRow]:
    """Load proposals attached to any `AgentRun` belonging to this
    conversation, in the order they were created. Status and target_id are
    read fresh per turn so an inline approval is reflected immediately."""
    session_factory = request.app.state.session_factory
    async with session_scope(session_factory) as session:
        stmt = (
            select(
                Proposal.id,
                Proposal.action,
                Proposal.target_type,
                Proposal.payload_json,
                Proposal.status,
                Proposal.target_id,
            )
            .join(AgentRun, Proposal.agent_run_id == AgentRun.id)
            .where(AgentRun.conversation_id == conversation_id)
            .order_by(Proposal.created_at)
        )
        rows = (await session.execute(stmt)).all()
    return [
        _ProposalRow(
            proposal_id=r[0],
            action=r[1],
            target_type=r[2],
            payload=r[3] or {},
            status=r[4],
            target_id=r[5],
        )
        for r in rows
    ]


async def _history_messages(
    request: Request,
    conversation_id: UUID,
    *,
    inline_budget: int,
    history_limit: int,
) -> tuple[list[LLMMessage], int]:
    """Reload prior `Message` rows for a conversation and convert them into
    LLM messages, inlining recent image attachments where budget allows."""
    session_factory = request.app.state.session_factory
    async with session_scope(session_factory) as session:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .limit(history_limit)
        )
        rows = list((await session.execute(stmt)).scalars().all())

    # Walk newest-to-oldest to spend the inline image budget on the most
    # recently attached images first, then re-sort into chronological order
    # for the LLM input.
    enriched: list[tuple[Message, list[_ResolvedAttachment]]] = []
    remaining = inline_budget
    for m in reversed(rows):
        if m.role != MessageRole.user:
            enriched.append((m, []))
            continue
        doc_ids = _user_attachment_doc_ids(m.content_json or [])
        if not doc_ids:
            enriched.append((m, []))
            continue
        resolved, remaining = await _resolve_attachments(request, doc_ids, inline_budget=remaining)
        enriched.append((m, resolved))

    enriched.reverse()

    messages: list[LLMMessage] = []
    for m, resolved in enriched:
        if m.role == MessageRole.user:
            text = _text_from_blocks(m.content_json or [])
            blocks = _content_blocks_for_user_turn(text, resolved)
            if blocks:
                messages.append(LLMMessage(role="user", content=blocks))
        elif m.role == MessageRole.assistant:
            messages.extend(_assistant_messages_from_content(m.content_json or []))
    return messages, remaining


async def _build_messages(
    req: ChatRequest,
    request: Request,
    *,
    conversation_id: UUID,
) -> tuple[list[LLMMessage], list[_ResolvedAttachment]]:
    """Build the LLM input for this turn. Past turns are reloaded from the DB
    so the server is the source of truth for history. Returns the LLM messages
    and the resolved attachment list for the current turn (used by the caller
    to persist structured attachment blocks on the user `Message` row)."""
    settings = request.app.state.settings
    cap = settings.chat_max_inline_images
    history_limit = settings.chat_history_message_limit

    # Two independent reads: history opens its own session and fans out image
    # fetches; proposals open a separate session for the AgentRun JOIN. Run
    # them concurrently. Each call uses its own `session_scope`, so this
    # honors the `AsyncSession is not concurrency-safe` constraint.
    (history, remaining), proposal_rows = await asyncio.gather(
        _history_messages(
            request,
            conversation_id,
            inline_budget=cap,
            history_limit=history_limit,
        ),
        _proposal_rows_for_conversation(request, conversation_id),
    )

    current_doc_ids = [a.document_id for a in req.attachments]
    current_resolved, _ = await _resolve_attachments(
        request,
        current_doc_ids,
        inline_budget=remaining,
    )
    current_blocks: list[ContentBlock] = _content_blocks_for_user_turn(
        req.message, current_resolved
    )
    if not current_blocks:
        current_blocks = [TextBlock(type="text", text=req.message)]

    session_state_text = _format_session_state(proposal_rows)

    messages = list(history)
    if session_state_text:
        log.info(
            "chat.session_state",
            conversation_id=str(conversation_id),
            proposal_count=len(proposal_rows),
            bytes=len(session_state_text),
        )
        messages.append(
            LLMMessage(
                role="user",
                content=[TextBlock(type="text", text=session_state_text)],
            )
        )
    messages.append(LLMMessage(role="user", content=current_blocks))
    return messages, current_resolved


def _user_content_json(
    req: ChatRequest, resolved: list[_ResolvedAttachment]
) -> list[dict[str, Any]]:
    """Build the structured content_json for the persisted user message: the
    clean user text plus an attachment block per ref. The bracket suffix is
    never stored; it is reconstructed each turn by `_build_messages`."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": req.message}]
    for r in resolved:
        blocks.append(
            {
                "type": "attachment",
                "document_id": str(r.ref.document_id),
                "filename": r.ref.filename,
                "mime_type": r.ref.mime_type,
                "kind": r.ref.kind,
            }
        )
    return blocks


async def _persist_turn(
    request: Request,
    *,
    conversation_id: UUID,
    user_content_json: list[dict[str, Any]],
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
            content_json=user_content_json,
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

    messages, current_resolved = await _build_messages(
        req, request, conversation_id=conversation_id
    )
    async for evt in agent.run_turn(messages):
        aggregator.consume(evt)
        if evt.type == "error":
            log.warning("chat.agent_error", message=aggregator.error_message)

    await _persist_turn(
        request,
        conversation_id=conversation_id,
        user_content_json=_user_content_json(req, current_resolved),
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
        current_resolved: list[_ResolvedAttachment] = []
        try:
            messages, current_resolved = await _build_messages(
                req, request, conversation_id=conversation_id
            )
            async for evt in agent.run_turn(messages):
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
                user_content_json=_user_content_json(req, current_resolved),
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
