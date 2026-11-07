"""The database tables (ARCHITECTURE.md section 11), as SQLAlchemy models.

Eight tables: the six named in the architecture, `app_settings` for the Settings page, and
`plate_corrections` for operators' corrections.
PostgreSQL stores facts and references only; video files and crop images live under
`storage/`, and the columns ending in `_path` point at them, relative to the project root.

How the tables relate:

    videos ──< processing_jobs ──< vehicle_tracks ──< plate_observations
                                        │
                                        └──1 recognition_events
                                        └──< plate_corrections (human corrections, kept beside the system's answer)
    demo_registry (fictional; matched to recognition_events by registration number)
    app_settings  (key → value)

One video can be processed more than once; each run is a job, and a video's results are
those of its latest completed job. Track ids are local to a job: `vehicle_tracks.track_id`
is the `T<n>` number in the annotated video and means nothing outside that job.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONColumn = JSON().with_variant(JSONB(), "postgresql")
"""JSONB on PostgreSQL; plain JSON elsewhere, so the tests can run on SQLite."""

# processing_jobs.status
QUEUED = "queued"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"
JOB_STATUSES = (QUEUED, PROCESSING, COMPLETED, FAILED)

# videos.source
UPLOADED = "upload"  # through the dashboard or POST /api/videos
INGESTED = "ingest"  # a file already on disk, registered without copying
COMMAND_LINE = "cli"  # `tracko-anpr process`


class Base(DeclarativeBase):
    pass


class Video(Base):
    """One video file known to the system. Its results are those of its latest completed job."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    """Folder name under storage/ for this video's results (the file name without extension, made unique)."""
    original_filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(Text)
    """Where the video is, relative to the project root when it lies inside it."""
    source: Mapped[str] = mapped_column(String(20), default=UPLOADED)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    fps: Mapped[str] = mapped_column(String(30))
    """The exact frame rate as a fraction, e.g. '30000/1001'."""
    fps_decimal: Mapped[float] = mapped_column(Float)
    frame_count: Mapped[int] = mapped_column(Integer)
    duration_s: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    plate_check: Mapped[dict | None] = mapped_column(JSONColumn)
    """The plate-size check (services/videos.py): status pending | running | done | failed, times, worker,
    error, and the result (pipeline/plate_check.py). The worker serves pending checks before queued jobs."""

    jobs: Mapped[list[ProcessingJob]] = relationship(back_populates="video", cascade="all, delete-orphan")


class ProcessingJob(Base):
    """One run of the pipeline over one video. The table is also the worker's queue."""

    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=QUEUED, index=True)
    stage: Mapped[str | None] = mapped_column(String(40))
    """The stage in progress or last finished; one of pipeline.runner.STAGES."""
    stage_done: Mapped[int] = mapped_column(Integer, default=0)
    stage_total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Last time the worker reported on this job; a stale heartbeat means the worker died."""
    worker_id: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    """How many times a worker has started this job. A job found half-done when a worker starts
    goes back in the queue once; the second time it is failed."""
    error: Mapped[str | None] = mapped_column(Text)
    settings: Mapped[dict | None] = mapped_column(JSONColumn)
    """Snapshot of the pipeline settings this job ran with."""
    timings: Mapped[dict | None] = mapped_column(JSONColumn)
    """Seconds per stage, as in results.json."""
    memory: Mapped[dict | None] = mapped_column(JSONColumn)
    processing_seconds: Mapped[float | None] = mapped_column(Float)
    """Wall-clock time of the whole run; also inside `timings`, kept as a column for averages."""
    frames_processed: Mapped[int | None] = mapped_column(Integer)
    plates_examined: Mapped[int | None] = mapped_column(Integer)
    output_dir: Mapped[str | None] = mapped_column(Text)
    annotated_video_path: Mapped[str | None] = mapped_column(Text)
    results_path: Mapped[str | None] = mapped_column(Text)
    detections_path: Mapped[str | None] = mapped_column(Text)
    plates_path: Mapped[str | None] = mapped_column(Text)

    video: Mapped[Video] = relationship(back_populates="jobs")
    tracks: Mapped[list[VehicleTrack]] = relationship(back_populates="job", cascade="all, delete-orphan")


class VehicleTrack(Base):
    """One track the tracker produced in one job: a vehicle followed from frame to frame."""

    __tablename__ = "vehicle_tracks"
    __table_args__ = (UniqueConstraint("job_id", "track_id", name="uq_vehicle_tracks_job_track"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[int] = mapped_column(Integer)
    """The tracker's id, shown as T<n>. Local to the job, never a permanent vehicle identity."""
    vehicle_type: Mapped[str] = mapped_column(String(20))
    """Car, Motorcycle, Bus or Truck: the class settled over the whole track."""
    detection_confidence: Mapped[float] = mapped_column(Float)
    """The detector's best confidence for this track."""
    first_frame: Mapped[int] = mapped_column(Integer)
    last_frame: Mapped[int] = mapped_column(Integer)
    frames_seen: Mapped[int] = mapped_column(Integer)
    first_seen_s: Mapped[float] = mapped_column(Float)
    last_seen_s: Mapped[float] = mapped_column(Float)
    countable: Mapped[bool] = mapped_column(Boolean, default=False)
    """Followed long enough and came near enough to count (pipeline/rules.py), and not the camera car."""
    camera_car: Mapped[bool] = mapped_column(Boolean, default=False)
    same_vehicle_as: Mapped[int | None] = mapped_column(Integer)
    """Track id (in this job) of an earlier track that is the same vehicle; such a track is not counted again."""
    counts_as_vehicle: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    """countable and not a repeat: adds one to Total Vehicles."""
    vehicle_crop_path: Mapped[str | None] = mapped_column(Text)
    approach: Mapped[str | None] = mapped_column(String(10))
    """'towards' or 'away' (from the camera), from the track's boxes (pipeline/direction.py); NULL: undetermined."""
    sideways: Mapped[str | None] = mapped_column(String(10))
    """'left' or 'right' across the picture; NULL when the vehicle hardly moved sideways."""

    job: Mapped[ProcessingJob] = relationship(back_populates="tracks")
    observations: Mapped[list[PlateObservation]] = relationship(back_populates="track", cascade="all, delete-orphan")
    recognition: Mapped[RecognitionEvent | None] = relationship(
        back_populates="track", cascade="all, delete-orphan", uselist=False
    )
    corrections: Mapped[list[PlateCorrection]] = relationship(back_populates="track", cascade="all, delete-orphan")


class PlateObservation(Base):
    """One plate found on one vehicle in one frame, and what the reader made of it."""

    __tablename__ = "plate_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_pk: Mapped[int] = mapped_column(ForeignKey("vehicle_tracks.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True)
    frame: Mapped[int] = mapped_column(Integer)
    time_s: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)
    """The plate's box in original-frame pixels."""
    detector_confidence: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(String(40), default="")
    """What the reader read, as returned (before look-alike correction); empty when unreadable."""
    ocr_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    unreadable: Mapped[bool] = mapped_column(Boolean, default=False)
    second_decoder_text: Mapped[str] = mapped_column(String(40), default="")
    found_in_track: Mapped[int] = mapped_column(Integer)
    """Track whose cut-out showed the plate; differs from the owner when a neighbour's cut-out found it."""
    crop_path: Mapped[str | None] = mapped_column(Text)

    track: Mapped[VehicleTrack] = relationship(back_populates="observations")


class RecognitionEvent(Base):
    """The validated outcome for one countable vehicle: its registration number, or why there is none."""

    __tablename__ = "recognition_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_pk: Mapped[int] = mapped_column(ForeignKey("vehicle_tracks.id", ondelete="CASCADE"), unique=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    """confirmed, unconfirmed or not_detected (pipeline/validation.py)."""
    registration_number: Mapped[str | None] = mapped_column(String(20), index=True)
    """Shown only as far as `status` supports it: a number with status unconfirmed is a best guess."""
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    """Average confidence of the readings that agreed; not a measure of accuracy."""
    support: Mapped[int] = mapped_column(Integer, default=0)
    """How many frames agreed on the number."""
    readings: Mapped[int] = mapped_column(Integer, default=0)
    """How many readings were confident enough to vote."""
    share: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    plate_crop_path: Mapped[str | None] = mapped_column(Text)

    track: Mapped[VehicleTrack] = relationship(back_populates="recognition")


class PlateCorrection(Base):
    """A human's correction of one detection's number or vehicle type, kept beside the system's answer.

    One row per correction made; the newest row for a track is the current correction. The
    system's own result in `recognition_events` and `vehicle_tracks` is never changed, so the
    dashboard's figures stay the pipeline's, and system and human answers can be compared later
    (ARCHITECTURE.md, "How to measure real accuracy").
    """

    __tablename__ = "plate_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_pk: Mapped[int] = mapped_column(ForeignKey("vehicle_tracks.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    system_number: Mapped[str | None] = mapped_column(String(20))
    """The number the pipeline had settled on when the correction was made."""
    system_status: Mapped[str] = mapped_column(String(20))
    system_type: Mapped[str] = mapped_column(String(20))
    corrected_number: Mapped[str | None] = mapped_column(String(20))
    """Normalised and format-checked; None when only the type was corrected."""
    corrected_type: Mapped[str | None] = mapped_column(String(20))
    """One of the four classes; None when only the number was corrected."""
    corrected_by: Mapped[str] = mapped_column(String(100), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    track: Mapped[VehicleTrack] = relationship(back_populates="corrections")


class DemoRegistryEntry(Base):
    """A FICTIONAL vehicle registration for the demonstration. No real registry is consulted, ever."""

    __tablename__ = "demo_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_number: Mapped[str] = mapped_column(String(20), unique=True)
    owner_name: Mapped[str] = mapped_column(String(100))
    vehicle_description: Mapped[str] = mapped_column(String(100))
    """Make and model, e.g. 'Maruti Suzuki Swift'."""
    vehicle_type: Mapped[str] = mapped_column(String(20))
    colour: Mapped[str] = mapped_column(String(30))
    registered_at: Mapped[str] = mapped_column(String(60))
    """Fictional registering office, e.g. 'Ernakulam RTO'."""
    valid_until: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(Text, default="")
    """Provenance, written by the seeder or the import ("Fictional record generated…", "Added from the dashboard…")."""
    description: Mapped[str | None] = mapped_column(String(200))
    """An operator's free text ("visitor pass until Friday"); nothing else reads it."""
    list_name: Mapped[str | None] = mapped_column(String(40))
    """The named list the record belongs to ("Staff", "Visitors", "Watch"), if any."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSetting(Base):
    """A value from the Settings page. Jobs keep their own snapshot, so changing one does not rewrite history."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONColumn)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


Index("ix_recognition_events_video_status", RecognitionEvent.video_id, RecognitionEvent.status)
Index("ix_vehicle_tracks_video_counts", VehicleTrack.video_id, VehicleTrack.counts_as_vehicle)
