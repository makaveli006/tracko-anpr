"""Processing jobs: starting one and reporting on it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracko_anpr.db.models import PROCESSING, ProcessingJob, Video
from tracko_anpr.db.store import queue_job
from tracko_anpr.pipeline.runner import STAGES

STALE_HEARTBEAT_SECONDS = 60
"""A running job whose worker has not reported for this long is shown as stalled."""


class VideoNotFound(LookupError):
    pass


@dataclass(frozen=True)
class StageState:
    name: str
    status: str
    """pending, running or done."""
    done: int
    total: int


@dataclass(frozen=True)
class JobStatus:
    id: int
    video_id: int
    video_name: str
    status: str
    stage: str | None
    stage_index: int | None
    """0-based position of `stage` in the seven-stage timeline."""
    stage_done: int
    stage_total: int
    progress: float
    """Overall share done, 0 to 1, over the seven stages."""
    stages: list[StageState]
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    stalled: bool
    """Running, but the worker has not reported for STALE_HEARTBEAT_SECONDS."""
    processing_seconds: float | None
    timings: dict | None
    memory: dict | None
    error: str | None
    annotated_video_path: str | None


def start_processing(session: Session, video_id: int) -> tuple[JobStatus, bool]:
    """Queue the video for the worker. Returns (job, created); a pending job is reused."""
    video = session.get(Video, video_id)
    if video is None:
        raise VideoNotFound(f"No video with id {video_id}.")
    job, created = queue_job(session, video)
    return describe(job), created


def get_job(session: Session, job_id: int) -> JobStatus | None:
    job = session.get(ProcessingJob, job_id)
    return None if job is None else describe(job)


def list_jobs(session: Session, limit: int = 50) -> list[JobStatus]:
    jobs = session.scalars(select(ProcessingJob).order_by(ProcessingJob.id.desc()).limit(limit)).all()
    return [describe(job) for job in jobs]


def describe(job: ProcessingJob, now: datetime | None = None) -> JobStatus:
    now = now or datetime.now(UTC)
    index = STAGES.index(job.stage) if job.stage in STAGES else None
    stages = []
    for position, name in enumerate(STAGES):
        if job.status == "completed" or (index is not None and position < index):
            stages.append(StageState(name, "done", 1, 1))
        elif index is not None and position == index and job.status == PROCESSING:
            stages.append(StageState(name, "running", job.stage_done, job.stage_total))
        elif index is not None and position == index:
            stages.append(
                StageState(
                    name,
                    "done" if job.stage_total and job.stage_done >= job.stage_total else "pending",
                    job.stage_done,
                    job.stage_total,
                )
            )
        else:
            stages.append(StageState(name, "pending", 0, 0))
    within = job.stage_done / job.stage_total if job.stage_total else 0.0
    if job.status == "completed":
        progress = 1.0
    elif index is None:
        progress = 0.0
    else:
        progress = (index + min(within, 1.0)) / len(STAGES)
    heartbeat = job.heartbeat_at
    stalled = (
        job.status == PROCESSING
        and heartbeat is not None
        and (now - _aware(heartbeat)).total_seconds() > STALE_HEARTBEAT_SECONDS
    )
    return JobStatus(
        id=job.id,
        video_id=job.video_id,
        video_name=job.video.name,
        status=job.status,
        stage=job.stage,
        stage_index=index,
        stage_done=job.stage_done,
        stage_total=job.stage_total,
        progress=round(progress, 4),
        stages=stages,
        attempts=job.attempts,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        heartbeat_at=heartbeat,
        stalled=stalled,
        processing_seconds=job.processing_seconds,
        timings=job.timings,
        memory=job.memory,
        error=job.error,
        annotated_video_path=job.annotated_video_path,
    )


def _aware(moment: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat them as UTC, which is what was stored."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
