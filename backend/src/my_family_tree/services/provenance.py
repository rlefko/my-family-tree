"""Provenance writer.

When a chat-asserted proposal is approved, we materialize a synthetic
`Source(kind=user_assertion)` and one `Claim` per asserted predicate.
Approved claims write a `FactProvenance` row so a future "why do we believe
X?" query resolves to the originating chat turn."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.models.claim import Claim, FactProvenance
from my_family_tree.models.enums import ClaimKind, ClaimStatus, SourceKind, SubjectType
from my_family_tree.models.source import Source

CHAT_EXTRACTOR = "chat"
PROVENANCE_CONFIDENCE = 70


async def get_or_create_chat_source(
    session: AsyncSession,
    *,
    tree_id: UUID,
    conversation_id: UUID | None,
    occurred_at: datetime | None = None,
) -> Source:
    """Return today's chat source for `(tree_id, conversation_id)`, creating
    one if needed. Same-day chat turns reuse a single Source so the claim
    table doesn't bloat with one Source per turn."""
    stamp = (occurred_at or datetime.now(UTC)).date().isoformat()
    title = f"Chat {stamp}"
    if conversation_id is not None:
        title = f"Chat {stamp} ({conversation_id})"

    stmt = select(Source).where(
        Source.tree_id == tree_id,
        Source.kind == SourceKind.user_assertion,
        Source.title == title,
    )
    found = (await session.execute(stmt)).scalar_one_or_none()
    if found is not None:
        return found

    source = Source(
        tree_id=tree_id,
        kind=SourceKind.user_assertion,
        title=title,
        repository="chat",
        meta_json={
            "conversation_id": str(conversation_id) if conversation_id else None,
            "date": stamp,
        },
    )
    session.add(source)
    await session.flush()
    return source


async def write_user_claims(
    session: AsyncSession,
    *,
    tree_id: UUID,
    source: Source,
    subject_type: SubjectType,
    subject_id: UUID,
    facts: dict[str, Any],
    kind: ClaimKind = ClaimKind.person_attr,
    confidence: int = PROVENANCE_CONFIDENCE,
    actor: str = "user",
) -> list[Claim]:
    """Insert one `Claim` row per fact and link each to a fresh
    `FactProvenance` row. Claims are inserted with `status=accepted` because
    they came from an explicit user assertion that the user already approved."""
    claims: list[Claim] = []
    now = datetime.now(UTC)
    for predicate, value in facts.items():
        if value is None:
            continue
        claim = Claim(
            tree_id=tree_id,
            kind=kind,
            status=ClaimStatus.accepted,
            subject_type=subject_type,
            subject_id=subject_id,
            predicate=predicate,
            object_json={"value": value},
            source_id=source.id,
            extractor=CHAT_EXTRACTOR,
            confidence=confidence,
            accepted_at=now,
            accepted_by=actor,
        )
        session.add(claim)
        await session.flush()
        session.add(
            FactProvenance(
                subject_type=subject_type,
                subject_id=subject_id,
                predicate=predicate,
                claim_id=claim.id,
            )
        )
        claims.append(claim)
    return claims
