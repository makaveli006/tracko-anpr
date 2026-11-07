"""processing_jobs.attempts: how many times a worker has started a job (Phase 9, the worker).

Revision ID: ba9303988888
Revises: fc32b7b47ec6
Create Date: 2026-11-07 00:29:24.052647

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ba9303988888"
down_revision: str | Sequence[str] | None = "fc32b7b47ec6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("processing_jobs", "attempts")
