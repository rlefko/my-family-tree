"""Person deduplication.

Two-stage:
1. Blocking: cheap candidate fetch via trigram similarity on surname plus
   birth daterange overlap.
2. Scoring: Jaro-Winkler on given names + date overlap + place distance +
   parent overlap + sex match. Threshold >=0.85 -> auto-merge proposal;
   0.6..0.85 -> conflict(kind=duplicate_person)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.models.enums import PersonStatus, Sex
from my_family_tree.models.person import Person


@dataclass(slots=True)
class DedupCandidate:
    person_id: UUID
    display_name: str


@dataclass(slots=True)
class DedupScore:
    candidate: DedupCandidate
    score: float
    components: dict[str, float]


async def block_candidates(
    session: AsyncSession,
    *,
    tree_id: UUID,
    surname: str | None,
    given_names: str | None,
    birth_min: date | None,
    birth_max: date | None,
    exclude_person_id: UUID | None = None,
    limit: int = 50,
) -> list[Person]:
    stmt = select(Person).where(
        Person.tree_id == tree_id,
        Person.status == PersonStatus.active,
    )
    if exclude_person_id is not None:
        stmt = stmt.where(Person.id != exclude_person_id)
    if surname:
        stmt = stmt.where(
            or_(Person.surname.ilike(f"%{surname}%"), Person.surname_at_birth.ilike(f"%{surname}%"))
        )
    elif given_names:
        stmt = stmt.where(Person.given_names.ilike(f"%{given_names}%"))
    if birth_min and birth_max:
        # daterange overlap with `&&` operator on a custom expression is
        # heavier; for v1 we use a +/- 5 year window comparison on min/max.
        stmt = stmt.where(
            or_(
                Person.birth_min.is_(None),
                Person.birth_max.is_(None),
                ~((Person.birth_max < birth_min) | (Person.birth_min > birth_max)),
            )
        )
    return list((await session.execute(stmt.limit(limit))).scalars().all())


def score_candidates(
    *,
    target_given: str | None,
    target_surname: str | None,
    target_birth: tuple[date | None, date | None],
    target_sex: Sex,
    candidates: list[Person],
) -> list[DedupScore]:
    target_min, target_max = target_birth
    out: list[DedupScore] = []
    for cand in candidates:
        comps: dict[str, float] = {}
        comps["given"] = (
            fuzz.WRatio(target_given or "", cand.given_names or "") / 100.0
            if (target_given or cand.given_names)
            else 0.0
        )
        comps["surname"] = (
            fuzz.WRatio(target_surname or "", cand.surname or "") / 100.0
            if (target_surname or cand.surname)
            else 0.0
        )
        comps["dates"] = _date_overlap_score(target_min, target_max, cand.birth_min, cand.birth_max)
        comps["sex"] = 1.0 if cand.sex == target_sex else 0.5
        # weighted sum: name 0.5, dates 0.3, sex 0.2
        score = (
            0.25 * comps["given"]
            + 0.25 * comps["surname"]
            + 0.30 * comps["dates"]
            + 0.20 * comps["sex"]
        )
        out.append(
            DedupScore(
                candidate=DedupCandidate(person_id=cand.id, display_name=cand.display_name),
                score=score,
                components=comps,
            )
        )
    return sorted(out, key=lambda s: s.score, reverse=True)


def _date_overlap_score(
    a_min: date | None,
    a_max: date | None,
    b_min: date | None,
    b_max: date | None,
) -> float:
    if not (a_min and a_max and b_min and b_max):
        return 0.5
    latest_start = max(a_min, b_min)
    earliest_end = min(a_max, b_max)
    if latest_start > earliest_end:
        return 0.0
    overlap_days = (earliest_end - latest_start).days + 1
    span_days = max((a_max - a_min).days, (b_max - b_min).days, 1) + 1
    return min(overlap_days / span_days, 1.0)
