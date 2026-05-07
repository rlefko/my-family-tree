"""Proposal endpoints: list, approve, reject, approve_batch. Approving a
proposal calls the applier in `services/proposal_apply.py` to materialize
the canonical entity. The agent never approves its own proposals; that's
exclusively a human action via this API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from my_family_tree.api.deps import SessionDep
from my_family_tree.core.errors import MFTError, NotFoundError, ValidationError
from my_family_tree.core.logging import get_logger
from my_family_tree.core.time import utcnow
from my_family_tree.models.agent_run import AgentRun
from my_family_tree.models.enums import ProposalAction, ProposalStatus, SubjectType
from my_family_tree.models.proposal import Proposal
from my_family_tree.services.proposal_apply import apply_proposal

log = get_logger(__name__)

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
    apply_error: str | None = None


class ProposalList(BaseModel):
    items: list[ProposalRow]


class ApproveBody(BaseModel):
    by: str = "user"


class ApproveBatchBody(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=500)
    by: str = "user"


class ApproveBatchResultRow(BaseModel):
    proposal_id: UUID
    status: str
    target_id: UUID | None = None
    error: str | None = None


class ApproveBatchResult(BaseModel):
    results: list[ApproveBatchResultRow]


# Apply order: leaf entities (place, source) before their referrers, then
# people, then relationships/events that may point at people, then claim/
# conflict updates last.
_APPLY_ORDER: dict[tuple[ProposalAction, SubjectType | None], int] = {
    (ProposalAction.create, SubjectType.place): 0,
    (ProposalAction.create, None): 1,  # source proposals
    (ProposalAction.create, SubjectType.document): 1,
    (ProposalAction.create, SubjectType.person): 2,
    (ProposalAction.update, SubjectType.person): 3,
    (ProposalAction.merge, SubjectType.person): 3,
    (ProposalAction.create, SubjectType.relationship): 4,
    (ProposalAction.delete, SubjectType.relationship): 4,
    (ProposalAction.create, SubjectType.event): 5,
    (ProposalAction.update, SubjectType.event): 5,
    (ProposalAction.accept_claim, None): 6,
    (ProposalAction.reject_claim, None): 6,
    (ProposalAction.resolve_conflict, None): 7,
}


async def _conversation_id_for(session: AsyncSession, proposal: Proposal) -> UUID | None:
    """Return the conversation_id this proposal originated from, by way of its
    agent_run. Used at apply time so synthetic chat-source provenance dedups
    per-conversation rather than collapsing every chat assertion onto one row."""
    if proposal.agent_run_id is None:
        return None
    run = await session.get(AgentRun, proposal.agent_run_id)
    return run.conversation_id if run is not None else None


def _row(p: Proposal) -> ProposalRow:
    return ProposalRow(
        id=p.id,
        action=p.action.value,
        target_type=p.target_type.value if p.target_type else None,
        target_id=p.target_id,
        status=p.status.value,
        rationale=p.rationale_md,
        confidence=p.confidence,
        payload=p.payload_json,
        apply_error=p.apply_error,
    )


@router.get("/proposals", response_model=ProposalList)
async def list_proposals(
    session: SessionDep,
    status: ProposalStatus | None = None,
    limit: int = 100,
) -> ProposalList:
    """When `status` is omitted, returns proposals across every status so the
    chat's inline-proposals surface can keep displaying a row that's been
    approved or rejected (showing the resolved badge instead of vanishing).
    The /proposals page passes `?status=pending` explicitly when it wants
    only the queue."""
    stmt = select(Proposal)
    if status is not None:
        stmt = stmt.where(Proposal.status == status)
    stmt = stmt.order_by(Proposal.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return ProposalList(items=[_row(p) for p in rows])


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalRow)
async def approve_proposal(
    proposal_id: UUID,
    body: ApproveBody,
    session: SessionDep,
) -> ProposalRow:
    p = await session.get(Proposal, proposal_id)
    if p is None:
        raise NotFoundError(f"proposal {proposal_id} not found")
    if p.status != ProposalStatus.pending:
        raise ValidationError(
            f"proposal is {p.status.value}, only pending proposals can be approved"
        )

    conversation_id = await _conversation_id_for(session, p)
    savepoint = await session.begin_nested()
    try:
        target_id = await apply_proposal(session, p, actor=body.by, conversation_id=conversation_id)
        await savepoint.commit()
    except MFTError as e:
        await savepoint.rollback()
        p.apply_error = str(e)
        log.warning("proposal.apply_failed", proposal_id=str(p.id), error=str(e))
        raise HTTPException(status_code=e.status_code, detail=str(e)) from e
    except Exception as e:
        await savepoint.rollback()
        p.apply_error = repr(e)
        log.exception("proposal.apply_unhandled", proposal_id=str(p.id))
        raise HTTPException(status_code=500, detail=str(e)) from e

    p.status = ProposalStatus.approved
    p.approved_at = utcnow()
    p.approved_by = body.by
    p.applied_at = utcnow()
    p.target_id = target_id
    p.apply_error = None
    return _row(p)


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
    return _row(p)


@router.post("/proposals/approve_batch", response_model=ApproveBatchResult)
async def approve_proposals_batch(
    body: ApproveBatchBody,
    session: SessionDep,
) -> ApproveBatchResult:
    """Approve several proposals in dependency order. Per-id savepoints
    preserve partial success: a failure on one id leaves earlier successes
    intact and continues with the rest."""
    proposals: list[Proposal] = []
    for pid in body.ids:
        p = await session.get(Proposal, pid)
        if p is None:
            proposals.append(None)  # type: ignore[arg-type]
        else:
            proposals.append(p)

    paired = list(zip(body.ids, proposals, strict=True))
    paired.sort(
        key=lambda pair: _APPLY_ORDER.get(
            (pair[1].action, pair[1].target_type) if pair[1] else (ProposalAction.create, None),
            99,
        )
    )

    results: list[ApproveBatchResultRow] = []
    for pid, p in paired:
        if p is None:
            results.append(
                ApproveBatchResultRow(proposal_id=pid, status="not_found", error="missing")
            )
            continue
        if p.status != ProposalStatus.pending:
            results.append(
                ApproveBatchResultRow(
                    proposal_id=pid,
                    status=p.status.value,
                    target_id=p.target_id,
                )
            )
            continue
        conversation_id = await _conversation_id_for(session, p)
        savepoint = await session.begin_nested()
        try:
            target_id = await apply_proposal(
                session, p, actor=body.by, conversation_id=conversation_id
            )
            await savepoint.commit()
        except Exception as e:
            await savepoint.rollback()
            p.apply_error = repr(e)
            results.append(
                ApproveBatchResultRow(
                    proposal_id=pid,
                    status="failed",
                    error=str(e),
                )
            )
            continue
        p.status = ProposalStatus.approved
        p.approved_at = utcnow()
        p.approved_by = body.by
        p.applied_at = utcnow()
        p.target_id = target_id
        p.apply_error = None
        results.append(
            ApproveBatchResultRow(
                proposal_id=pid,
                status="approved",
                target_id=target_id,
            )
        )
    return ApproveBatchResult(results=results)
