"""vehicle_tracks.approach and .sideways: the travel direction derived from a track's boxes (Axis item 3).

Revision ID: d41ec7a0b3f2
Revises: 9e4a635f9014
Create Date: 2026-11-07 07:05:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d41ec7a0b3f2"
down_revision: str | Sequence[str] | None = "9e4a635f9014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vehicle_tracks", sa.Column("approach", sa.String(length=10), nullable=True))
    op.add_column("vehicle_tracks", sa.Column("sideways", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicle_tracks", "sideways")
    op.drop_column("vehicle_tracks", "approach")
