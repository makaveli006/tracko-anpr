"""videos.plate_check: the plate-size check requested for, running on or finished for a video (Axis item 2).

Revision ID: e5a1c9d2b7f3
Revises: d41ec7a0b3f2
Create Date: 2026-11-07 08:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5a1c9d2b7f3"
down_revision: str | Sequence[str] | None = "d41ec7a0b3f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column(
            "plate_check",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("videos", "plate_check")
