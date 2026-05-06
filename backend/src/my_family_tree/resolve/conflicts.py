"""Conflict detection rules. Each rule is a pure function over the current
DB state, idempotent, and produces stable IDs so re-detection updates the
existing row instead of duplicating."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.models.claim import Claim
from my_family_tree.models.enums import (
    ClaimStatus,
    ConflictKind,
    SubjectType,
)


@dataclass(slots=True)
class ConflictCandidate:
    id: UUID
    kind: ConflictKind
    subject_type: SubjectType
    subject_id: UUID
    summary: str
    severity: int
    detected_by: str
    claim_ids: list[UUID]


def stable_conflict_id(
    *,
    kind: ConflictKind,
    subject_ids: list[UUID],
    predicate: str | None = None,
) -> UUID:
    h = hashlib.sha256()
    h.update(kind.value.encode())
    h.update(b"|")
    for sid in sorted(subject_ids):
        h.update(str(sid).encode())
        h.update(b",")
    if predicate:
        h.update(b"|")
        h.update(predicate.encode())
    return UUID(h.hexdigest()[:32])


async def detect_conflicts_for_person(
    session: AsyncSession,
    *,
    tree_id: UUID,
    person_id: UUID,
) -> list[ConflictCandidate]:
    """Run the full v1 rule set against one person. Returns candidate conflict
    rows; the caller upserts them on the `conflict` table."""
    out: list[ConflictCandidate] = []
    out.extend(await _date_mismatch(session, tree_id=tree_id, person_id=person_id))
    return out


async def _date_mismatch(
    session: AsyncSession,
    *,
    tree_id: UUID,
    person_id: UUID,
) -> list[ConflictCandidate]:
    """Two accepted claims for the same predicate (e.g. birth_date) whose
    `[date_min, date_max]` ranges don't overlap."""
    stmt = select(Claim).where(
        Claim.tree_id == tree_id,
        Claim.subject_type == SubjectType.person,
        Claim.subject_id == person_id,
        Claim.status == ClaimStatus.accepted,
    )
    claims = list((await session.execute(stmt)).scalars().all())
    by_pred: dict[str, list[Claim]] = {}
    for c in claims:
        by_pred.setdefault(c.predicate, []).append(c)

    min_for_conflict = 2
    out: list[ConflictCandidate] = []
    for predicate, group in by_pred.items():
        if len(group) < min_for_conflict:
            continue
        ranges: list[tuple[Claim, str | None, str | None]] = []
        for c in group:
            obj = c.object_json or {}
            ranges.append((c, obj.get("date_min"), obj.get("date_max")))
        # Pairwise non-overlap detection.
        for i, (c1, a_min, a_max) in enumerate(ranges):
            for c2, b_min, b_max in ranges[i + 1 :]:
                if a_min and a_max and b_min and b_max and (a_max < b_min or b_max < a_min):
                    out.append(
                        ConflictCandidate(
                            id=stable_conflict_id(
                                kind=ConflictKind.date_mismatch,
                                subject_ids=[person_id],
                                predicate=predicate,
                            ),
                            kind=ConflictKind.date_mismatch,
                            subject_type=SubjectType.person,
                            subject_id=person_id,
                            summary=(
                                f"Conflicting {predicate} claims: "
                                f"{a_min}..{a_max} vs {b_min}..{b_max}"
                            ),
                            severity=70,
                            detected_by="rule:date_mismatch",
                            claim_ids=[c1.id, c2.id],
                        )
                    )
    return out
