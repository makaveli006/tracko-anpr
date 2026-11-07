"""The seven tables: videos, processing_jobs, vehicle_tracks, plate_observations,
recognition_events, demo_registry and app_settings (ARCHITECTURE.md section 11).

Revision ID: fc32b7b47ec6
Revises:
Create Date: 2026-11-07 00:17:50.245671

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fc32b7b47ec6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column(
            "value", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "demo_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registration_number", sa.String(length=20), nullable=False),
        sa.Column("owner_name", sa.String(length=100), nullable=False),
        sa.Column("vehicle_description", sa.String(length=100), nullable=False),
        sa.Column("vehicle_type", sa.String(length=20), nullable=False),
        sa.Column("colour", sa.String(length=30), nullable=False),
        sa.Column("registered_at", sa.String(length=60), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registration_number"),
    )
    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fps", sa.String(length=30), nullable=False),
        sa.Column("fps_decimal", sa.Float(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=True),
        sa.Column("stage_done", sa.Integer(), nullable=False),
        sa.Column("stage_total", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "settings", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True
        ),
        sa.Column(
            "timings", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True
        ),
        sa.Column(
            "memory", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=True
        ),
        sa.Column("processing_seconds", sa.Float(), nullable=True),
        sa.Column("frames_processed", sa.Integer(), nullable=True),
        sa.Column("plates_examined", sa.Integer(), nullable=True),
        sa.Column("output_dir", sa.Text(), nullable=True),
        sa.Column("annotated_video_path", sa.Text(), nullable=True),
        sa.Column("results_path", sa.Text(), nullable=True),
        sa.Column("detections_path", sa.Text(), nullable=True),
        sa.Column("plates_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_processing_jobs_status"), "processing_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_processing_jobs_video_id"), "processing_jobs", ["video_id"], unique=False)
    op.create_table(
        "vehicle_tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_type", sa.String(length=20), nullable=False),
        sa.Column("detection_confidence", sa.Float(), nullable=False),
        sa.Column("first_frame", sa.Integer(), nullable=False),
        sa.Column("last_frame", sa.Integer(), nullable=False),
        sa.Column("frames_seen", sa.Integer(), nullable=False),
        sa.Column("first_seen_s", sa.Float(), nullable=False),
        sa.Column("last_seen_s", sa.Float(), nullable=False),
        sa.Column("countable", sa.Boolean(), nullable=False),
        sa.Column("camera_car", sa.Boolean(), nullable=False),
        sa.Column("same_vehicle_as", sa.Integer(), nullable=True),
        sa.Column("counts_as_vehicle", sa.Boolean(), nullable=False),
        sa.Column("vehicle_crop_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "track_id", name="uq_vehicle_tracks_job_track"),
    )
    op.create_index(op.f("ix_vehicle_tracks_counts_as_vehicle"), "vehicle_tracks", ["counts_as_vehicle"], unique=False)
    op.create_index(op.f("ix_vehicle_tracks_job_id"), "vehicle_tracks", ["job_id"], unique=False)
    op.create_index("ix_vehicle_tracks_video_counts", "vehicle_tracks", ["video_id", "counts_as_vehicle"], unique=False)
    op.create_index(op.f("ix_vehicle_tracks_video_id"), "vehicle_tracks", ["video_id"], unique=False)
    op.create_table(
        "plate_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_pk", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("frame", sa.Integer(), nullable=False),
        sa.Column("time_s", sa.Float(), nullable=False),
        sa.Column("x1", sa.Float(), nullable=False),
        sa.Column("y1", sa.Float(), nullable=False),
        sa.Column("x2", sa.Float(), nullable=False),
        sa.Column("y2", sa.Float(), nullable=False),
        sa.Column("detector_confidence", sa.Float(), nullable=False),
        sa.Column("text", sa.String(length=40), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=False),
        sa.Column("unreadable", sa.Boolean(), nullable=False),
        sa.Column("second_decoder_text", sa.String(length=40), nullable=False),
        sa.Column("found_in_track", sa.Integer(), nullable=False),
        sa.Column("crop_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_pk"], ["vehicle_tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plate_observations_job_id"), "plate_observations", ["job_id"], unique=False)
    op.create_index(op.f("ix_plate_observations_track_pk"), "plate_observations", ["track_pk"], unique=False)
    op.create_table(
        "recognition_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_pk", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("registration_number", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("support", sa.Integer(), nullable=False),
        sa.Column("readings", sa.Integer(), nullable=False),
        sa.Column("share", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("plate_crop_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_pk"], ["vehicle_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("track_pk"),
    )
    op.create_index(op.f("ix_recognition_events_job_id"), "recognition_events", ["job_id"], unique=False)
    op.create_index(
        op.f("ix_recognition_events_registration_number"), "recognition_events", ["registration_number"], unique=False
    )
    op.create_index(op.f("ix_recognition_events_status"), "recognition_events", ["status"], unique=False)
    op.create_index(op.f("ix_recognition_events_video_id"), "recognition_events", ["video_id"], unique=False)
    op.create_index("ix_recognition_events_video_status", "recognition_events", ["video_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recognition_events_video_status", table_name="recognition_events")
    op.drop_index(op.f("ix_recognition_events_video_id"), table_name="recognition_events")
    op.drop_index(op.f("ix_recognition_events_status"), table_name="recognition_events")
    op.drop_index(op.f("ix_recognition_events_registration_number"), table_name="recognition_events")
    op.drop_index(op.f("ix_recognition_events_job_id"), table_name="recognition_events")
    op.drop_table("recognition_events")
    op.drop_index(op.f("ix_plate_observations_track_pk"), table_name="plate_observations")
    op.drop_index(op.f("ix_plate_observations_job_id"), table_name="plate_observations")
    op.drop_table("plate_observations")
    op.drop_index(op.f("ix_vehicle_tracks_video_id"), table_name="vehicle_tracks")
    op.drop_index("ix_vehicle_tracks_video_counts", table_name="vehicle_tracks")
    op.drop_index(op.f("ix_vehicle_tracks_job_id"), table_name="vehicle_tracks")
    op.drop_index(op.f("ix_vehicle_tracks_counts_as_vehicle"), table_name="vehicle_tracks")
    op.drop_table("vehicle_tracks")
    op.drop_index(op.f("ix_processing_jobs_video_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_status"), table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_table("videos")
    op.drop_table("demo_registry")
    op.drop_table("app_settings")
