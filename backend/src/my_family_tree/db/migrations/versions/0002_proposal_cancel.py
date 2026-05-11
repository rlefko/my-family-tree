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
    op.add_column(
        "proposal",
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "proposal",
        sa.Column("cancel_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    # Postgres cannot drop a single enum value, so `canceled` stays in the type.
    op.drop_column("proposal", "cancel_reason")
    op.drop_column("proposal", "canceled_at")
