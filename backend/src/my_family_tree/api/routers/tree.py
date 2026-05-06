"""Tree-wide endpoints: stats."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from my_family_tree.api.deps import SessionDep
from my_family_tree.models.conflict import Conflict
from my_family_tree.models.document import Document
from my_family_tree.models.enums import ConflictStatus, PersonStatus, ProposalStatus
from my_family_tree.models.event import Event
from my_family_tree.models.person import Person
from my_family_tree.models.proposal import Proposal
from my_family_tree.models.relationship import Relationship

router = APIRouter()


class TreeStatsResponse(BaseModel):
    persons: int
    events: int
    relationships: int
    documents: int
    conflicts_open: int
    proposals_pending: int


@router.get("/tree/stats", response_model=TreeStatsResponse)
async def stats(session: SessionDep) -> TreeStatsResponse:
    persons = (
        await session.execute(
            select(func.count()).select_from(Person).where(Person.status == PersonStatus.active)
        )
    ).scalar_one()
    events = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
    rels = (await session.execute(select(func.count()).select_from(Relationship))).scalar_one()
    docs = (await session.execute(select(func.count()).select_from(Document))).scalar_one()
    conflicts_open = (
        await session.execute(
            select(func.count()).select_from(Conflict).where(Conflict.status == ConflictStatus.open)
        )
    ).scalar_one()
    proposals_pending = (
        await session.execute(
            select(func.count())
            .select_from(Proposal)
            .where(Proposal.status == ProposalStatus.pending)
        )
    ).scalar_one()
    return TreeStatsResponse(
        persons=int(persons),
        events=int(events),
        relationships=int(rels),
        documents=int(docs),
        conflicts_open=int(conflicts_open),
        proposals_pending=int(proposals_pending),
    )
