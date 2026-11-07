"""plate_corrections: operators' corrections of a detection's number or type, kept beside the system's result.

Revision ID: 9e4a635f9014
Revises: ba9303988888
Create Date: 2026-11-07 05:21:52.321116

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9e4a635f9014"
down_revision: str | Sequence[str] | None = "ba9303988888"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plate_corrections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_pk", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("system_number", sa.String(length=20), nullable=True),
        sa.Column("system_status", sa.String(length=20), nullable=False),
        sa.Column("system_type", sa.String(length=20), nullable=False),
        sa.Column("corrected_number", sa.String(length=20), nullable=True),
        sa.Column("corrected_type", sa.String(length=20), nullable=True),
        sa.Column("corrected_by", sa.String(length=100), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_pk"], ["vehicle_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plate_corrections_job_id"), "plate_corrections", ["job_id"], unique=False)
    op.create_index(op.f("ix_plate_corrections_track_pk"), "plate_corrections", ["track_pk"], unique=False)
    op.create_index(op.f("ix_plate_corrections_video_id"), "plate_corrections", ["video_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_plate_corrections_video_id"), table_name="plate_corrections")
    op.drop_index(op.f("ix_plate_corrections_track_pk"), table_name="plate_corrections")
    op.drop_index(op.f("ix_plate_corrections_job_id"), table_name="plate_corrections")
    op.drop_table("plate_corrections")
