"""Conflict endpoints: list, get, resolve."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from my_family_tree.api.deps import SessionDep
from my_family_tree.core.errors import NotFoundError
from my_family_tree.models.conflict import Conflict
from my_family_tree.models.enums import ConflictStatus

router = APIRouter()


class ConflictRow(BaseModel):
    id: UUID
    kind: str
    status: str
    severity: int
    summary: str
    subject_id: UUID
    subject_type: str


class ConflictList(BaseModel):
    items: list[ConflictRow]


@router.get("/conflicts", response_model=ConflictList)
async def list_conflicts(
    session: SessionDep,
    status: ConflictStatus | None = ConflictStatus.open,
    limit: int = 100,
) -> ConflictList:
    stmt = select(Conflict)
    if status is not None:
        stmt = stmt.where(Conflict.status == status)
    stmt = stmt.order_by(Conflict.severity.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return ConflictList(
        items=[
            ConflictRow(
                id=c.id,
                kind=c.kind.value,
                status=c.status.value,
                severity=c.severity,
                summary=c.summary,
                subject_id=c.subject_id,
                subject_type=c.subject_type.value,
            )
            for c in rows
        ]
    )


@router.get("/conflicts/{conflict_id}", response_model=ConflictRow)
async def get_conflict(conflict_id: UUID, session: SessionDep) -> ConflictRow:
    c = await session.get(Conflict, conflict_id)
    if c is None:
        raise NotFoundError(f"conflict {conflict_id} not found")
    return ConflictRow(
        id=c.id,
        kind=c.kind.value,
        status=c.status.value,
        severity=c.severity,
        summary=c.summary,
        subject_id=c.subject_id,
        subject_type=c.subject_type.value,
    )
