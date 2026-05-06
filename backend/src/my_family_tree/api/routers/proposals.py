"""Proposal endpoints: list, approve, reject. The agent never approves
its own proposals; that's exclusively a human action via this API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from my_family_tree.api.deps import SessionDep
from my_family_tree.core.errors import NotFoundError
from my_family_tree.core.time import utcnow
from my_family_tree.models.enums import ProposalStatus
from my_family_tree.models.proposal import Proposal

router = APIRouter()


class ProposalRow(BaseModel):
    id: UUID
    action: str
    target_type: str | None
    target_id: UUID | None
    status: str
    rationale: str | None = None
    confidence: int
    payload: dict[str, Any] | None = None


class ProposalList(BaseModel):
    items: list[ProposalRow]


@router.get("/proposals", response_model=ProposalList)
async def list_proposals(
    session: SessionDep,
    status: ProposalStatus | None = ProposalStatus.pending,
    limit: int = 100,
) -> ProposalList:
    stmt = select(Proposal)
    if status is not None:
        stmt = stmt.where(Proposal.status == status)
    stmt = stmt.order_by(Proposal.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return ProposalList(
        items=[
            ProposalRow(
                id=p.id,
                action=p.action.value,
                target_type=p.target_type.value if p.target_type else None,
                target_id=p.target_id,
                status=p.status.value,
                rationale=p.rationale_md,
                confidence=p.confidence,
                payload=p.payload_json,
            )
            for p in rows
        ]
    )


class ApproveBody(BaseModel):
    by: str = "user"


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalRow)
async def approve_proposal(
    proposal_id: UUID,
    body: ApproveBody,
    session: SessionDep,
) -> ProposalRow:
    p = await session.get(Proposal, proposal_id)
    if p is None:
        raise NotFoundError(f"proposal {proposal_id} not found")
    p.status = ProposalStatus.approved
    p.approved_at = utcnow()
    p.approved_by = body.by
    # Apply happens in a separate worker; for v1 we mark applied_at on the
    # same call once we wire the apply step (deferred).
    return ProposalRow(
        id=p.id,
        action=p.action.value,
        target_type=p.target_type.value if p.target_type else None,
        target_id=p.target_id,
        status=p.status.value,
        rationale=p.rationale_md,
        confidence=p.confidence,
        payload=p.payload_json,
    )


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalRow)
async def reject_proposal(
    proposal_id: UUID,
    body: ApproveBody,
    session: SessionDep,
) -> ProposalRow:
    p = await session.get(Proposal, proposal_id)
    if p is None:
        raise NotFoundError(f"proposal {proposal_id} not found")
    p.status = ProposalStatus.rejected
    p.approved_by = body.by
    return ProposalRow(
        id=p.id,
        action=p.action.value,
        target_type=p.target_type.value if p.target_type else None,
        target_id=p.target_id,
        status=p.status.value,
        rationale=p.rationale_md,
        confidence=p.confidence,
        payload=p.payload_json,
    )
