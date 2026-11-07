"""Writing a video, its jobs and a pipeline run's results to the database.

The pipeline itself knows nothing about the database: it returns a `PipelineResult` and
writes files. This module maps that result onto the tables, so the command line (now) and
the worker (Phase 9) store results the same way.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracko_anpr.db.models import (
    COMPLETED,
    FAILED,
    PROCESSING,
    QUEUED,
    PlateObservation,
    ProcessingJob,
    RecognitionEvent,
    VehicleTrack,
    Video,
)
from tracko_anpr.pipeline.results import frame_time
from tracko_anpr.pipeline.runner import relative_path

if TYPE_CHECKING:
    from tracko_anpr.pipeline.runner import PipelineResult
    from tracko_anpr.pipeline.video import VideoInfo


def now() -> datetime:
    return datetime.now(UTC)


def unique_video_name(session: Session, wanted: str, file_path: str) -> str:
    """`wanted` if it is free or already belongs to this same file; otherwise `wanted-2`, `wanted-3`, ..."""
    candidate, counter = wanted, 1
    while True:
        existing = session.scalar(select(Video).where(Video.name == candidate))
        if existing is None or existing.file_path == file_path:
            return candidate
        counter += 1
        candidate = f"{wanted}-{counter}"


def register_video(
    session: Session,
    info: VideoInfo,
    root: Path,
    source: str,
    name: str | None = None,
    original_filename: str | None = None,
) -> Video:
    """The `videos` row for this file, created if it is new.

    A file processed again keeps its row (same `name`), so its earlier jobs stay in its history.
    """
    file_path = relative_path(info.path.resolve(), root)
    name = unique_video_name(session, name or info.path.stem, file_path)
    video = session.scalar(select(Video).where(Video.name == name))
    if video is None:
        video = Video(name=name, original_filename=original_filename or info.path.name, source=source)
        session.add(video)
    video.file_path = file_path
    video.size_bytes = info.path.stat().st_size if info.path.is_file() else None
    video.width, video.height = info.width, info.height
    video.fps, video.fps_decimal = str(info.fps), round(info.fps_float, 6)
    video.frame_count, video.duration_s = info.frame_count, info.duration_s
    session.flush()
    return video


def create_job(session: Session, video: Video, status: str, settings: dict | None = None) -> ProcessingJob:
    job = ProcessingJob(video=video, status=status, settings=settings)
    if status == PROCESSING:
        job.started_at = job.heartbeat_at = now()
    session.add(job)
    session.flush()
    return job


def store_result(session: Session, job: ProcessingJob, result: PipelineResult, root: Path) -> None:
    """Record a finished run on its job: the job's figures, then one row per track, plate and decision.

    Rows from an earlier attempt at the same job are replaced.
    """
    document = result.document
    fps = result.info.fps_float
    for track in list(job.tracks):
        session.delete(track)
    session.flush()

    job.status = COMPLETED
    job.finished_at = now()
    job.stage = "result_generation"
    job.stage_done = job.stage_total = document.get("frames_processed", 0)
    job.settings = document.get("settings")
    job.timings = document.get("timings")
    job.memory = document.get("memory")
    job.processing_seconds = result.timings.get("total_s")
    job.frames_processed = document.get("frames_processed")
    job.plates_examined = document.get("plates_examined")
    job.error = None
    results_file = result.files.get("results")
    job.output_dir = relative_path(results_file.parent, root) if results_file else None
    job.results_path = relative_path(results_file, root)
    job.detections_path = relative_path(result.files.get("detections"), root)
    job.plates_path = relative_path(result.files.get("plates"), root)
    job.annotated_video_path = relative_path(result.files.get("annotated_video"), root)

    for vehicle in result.vehicles:
        track = VehicleTrack(
            job_id=job.id,
            video_id=job.video_id,
            track_id=vehicle.track_id,
            vehicle_type=vehicle.class_name,
            detection_confidence=round(vehicle.best_confidence, 4),
            first_frame=vehicle.first_frame,
            last_frame=vehicle.last_frame,
            frames_seen=vehicle.frames_seen,
            first_seen_s=round(frame_time(vehicle.first_frame, fps), 3),
            last_seen_s=round(frame_time(vehicle.last_frame, fps), 3),
            countable=vehicle.countable,
            camera_car=vehicle.camera_car,
            same_vehicle_as=vehicle.same_vehicle_as,
            counts_as_vehicle=vehicle.counts_as_vehicle,
            vehicle_crop_path=relative_path(vehicle.vehicle_crop, root),
        )
        session.add(track)
        session.flush()  # the track needs its id before its plates can point at it

        for sighting in vehicle.sightings:
            session.add(
                PlateObservation(
                    track_pk=track.id,
                    job_id=job.id,
                    frame=sighting.frame,
                    time_s=round(frame_time(sighting.frame, fps), 3),
                    x1=sighting.box[0],
                    y1=sighting.box[1],
                    x2=sighting.box[2],
                    y2=sighting.box[3],
                    detector_confidence=round(sighting.detector_confidence, 4),
                    text=sighting.text,
                    ocr_confidence=round(sighting.confidence, 4),
                    unreadable=sighting.unreadable,
                    second_decoder_text=sighting.ctc_text,
                    found_in_track=sighting.track_id if sighting.found_in is None else sighting.found_in,
                    crop_path=relative_path(sighting.crop_file, root),
                )
            )

        decision = vehicle.decision
        if decision is not None:  # every countable vehicle has a decision, even "not detected"
            session.add(
                RecognitionEvent(
                    track_pk=track.id,
                    job_id=job.id,
                    video_id=job.video_id,
                    status=decision.status,
                    registration_number=decision.text or None,
                    confidence=decision.confidence,
                    support=decision.support,
                    readings=decision.readings,
                    share=decision.share,
                    reason=decision.reason,
                    plate_crop_path=relative_path(vehicle.plate_crop, root),
                )
            )
    session.flush()


def queue_job(session: Session, video: Video) -> tuple[ProcessingJob, bool]:
    """Put a video in the queue. Returns (job, created): an existing queued or running job is reused."""
    pending = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.video_id == video.id, ProcessingJob.status.in_((QUEUED, PROCESSING)))
        .order_by(ProcessingJob.id)
    )
    if pending is not None:
        return pending, False
    return create_job(session, video, QUEUED), True


def find_video(session: Session, reference: str) -> Video | None:
    """A video by id or by name."""
    if reference.isdigit():
        return session.get(Video, int(reference))
    return session.scalar(select(Video).where(Video.name == reference))


def mark_failed(session: Session, job: ProcessingJob, error: str) -> None:
    job.status = FAILED
    job.error = error[:4000]
    job.finished_at = now()
    session.flush()
