"""proposal cancel: new status value and audit columns

Revision ID: 0002_proposal_cancel
Revises: 0001_init
Create Date: 2026-05-11 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_proposal_cancel"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE proposal_status ADD VALUE IF NOT EXISTS 'canceled'"))
    # 0001's `target_metadata.create_all` uses the current SQLModel definitions
    # so a fresh install already has these columns; IF NOT EXISTS keeps the
    # upgrade additive for older databases without colliding on fresh ones.
    op.execute(sa.text("ALTER TABLE proposal ADD COLUMN IF NOT EXISTS canceled_at timestamptz"))
    op.execute(sa.text("ALTER TABLE proposal ADD COLUMN IF NOT EXISTS cancel_reason text"))


def downgrade() -> None:
    # Postgres cannot drop a single enum value, so `canceled` stays in the type.
    op.drop_column("proposal", "cancel_reason")
    op.drop_column("proposal", "canceled_at")
