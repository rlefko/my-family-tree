"""Person merge mechanics. Rewrites every FK pointing at the loser to point at
the winner inside a single transaction, then marks the loser as `merged` with
`merged_into_id` set so historical IDs still resolve via redirect."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.core.errors import NotFoundError, ValidationError
from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.models.claim import Claim
from my_family_tree.models.enums import PersonStatus, SubjectType
from my_family_tree.models.event import EventParticipant
from my_family_tree.models.person import Alias, Person
from my_family_tree.models.relationship import Relationship

log = get_logger(__name__)


async def merge_persons(
    session: AsyncSession,
    *,
    tree_id: UUID,
    loser_id: UUID,
    winner_id: UUID,
) -> None:
    """Merge `loser_id` into `winner_id`. Both must belong to `tree_id`.

    All historical IDs remain resolvable: a later `person_get(loser_id)`
    follows `merged_into_id` and returns the winner.
    """
    if loser_id == winner_id:
        raise ValidationError("cannot merge a person into itself")

    loser = await session.get(Person, loser_id)
    winner = await session.get(Person, winner_id)
    if loser is None or loser.tree_id != tree_id:
        raise NotFoundError(f"loser {loser_id} not found in tree")
    if winner is None or winner.tree_id != tree_id:
        raise NotFoundError(f"winner {winner_id} not found in tree")

    # Rewrite every FK pointing at the loser.
    await session.execute(
        update(Relationship).where(Relationship.subject_id == loser_id).values(subject_id=winner_id)
    )
    await session.execute(
        update(Relationship).where(Relationship.object_id == loser_id).values(object_id=winner_id)
    )
    await session.execute(
        update(EventParticipant)
        .where(EventParticipant.person_id == loser_id)
        .values(person_id=winner_id)
    )
    await session.execute(
        update(Alias).where(Alias.person_id == loser_id).values(person_id=winner_id)
    )
    await session.execute(
        update(Claim)
        .where(
            Claim.subject_type == SubjectType.person,
            Claim.subject_id == loser_id,
        )
        .values(subject_id=winner_id)
    )

    loser.status = PersonStatus.merged
    loser.merged_into_id = winner_id
    loser.updated_at = utcnow()

    log.info(
        "person.merged",
        tree_id=str(tree_id),
        loser_id=str(loser_id),
        winner_id=str(winner_id),
    )
