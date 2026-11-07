"""Figures for the Analytics page and the Overview cards, for one video or all of them."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracko_anpr.db import metrics
from tracko_anpr.db.metrics import Summary, latest_completed_jobs
from tracko_anpr.db.models import ProcessingJob, RecognitionEvent, VehicleTrack, Video
from tracko_anpr.pipeline.validation import CONFIRMED

CONFIDENCE_BINS = [(0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 0.95), (0.95, 1.01)]


@dataclass(frozen=True)
class ProcessingRun:
    video_id: int
    video_name: str
    job_id: int
    duration_s: float
    """Length of the video."""
    processing_seconds: float
    frames: int
    detect_track_ms_per_frame: float | None
    """Average detection-and-tracking time per frame: the "inference latency". Includes the model's start-up."""
    ocr_ms_per_plate: float | None
    times_real_time: float | None


@dataclass(frozen=True)
class Analytics:
    scope: str
    """'video' or 'all'."""
    video_id: int | None
    summary: Summary
    by_class: dict[str, int]
    by_status: dict[str, int]
    detections_over_time: list[tuple[int, int]]
    """Only for one video (empty across all: their time axes differ)."""
    confidence_distribution: list[tuple[str, int]]
    """Confirmed numbers by confidence band, e.g. ('0.90–0.95', 12)."""
    runs: list[ProcessingRun]
    average_detect_track_ms_per_frame: float | None
    average_ocr_ms_per_plate: float | None


def analytics(session: Session, video_id: int | None = None) -> Analytics:
    jobs = latest_completed_jobs(video_id)
    confidences = session.scalars(
        select(RecognitionEvent.confidence)
        .join(VehicleTrack, VehicleTrack.id == RecognitionEvent.track_pk)
        .where(RecognitionEvent.job_id.in_(jobs), RecognitionEvent.status == CONFIRMED, VehicleTrack.counts_as_vehicle)
    ).all()
    distribution = []
    for low, high in CONFIDENCE_BINS:
        label = f"{low:.2f}–{min(high, 1.0):.2f}"
        distribution.append((label, sum(1 for c in confidences if low <= c < high)))

    runs = []
    rows = session.execute(
        select(ProcessingJob, Video).join(Video, Video.id == ProcessingJob.video_id).where(ProcessingJob.id.in_(jobs))
    ).all()
    for job, video in rows:
        timings = job.timings or {}
        frames = job.frames_processed or 0
        track_s = timings.get("detection_and_tracking_s")
        ocr_s = timings.get("ocr_s")
        runs.append(
            ProcessingRun(
                video_id=video.id,
                video_name=video.name,
                job_id=job.id,
                duration_s=video.duration_s,
                processing_seconds=job.processing_seconds or 0.0,
                frames=frames,
                detect_track_ms_per_frame=round(1000 * track_s / frames, 2) if track_s and frames else None,
                ocr_ms_per_plate=round(1000 * ocr_s / job.plates_examined, 1)
                if ocr_s and job.plates_examined
                else None,
                times_real_time=round(video.duration_s / job.processing_seconds, 2) if job.processing_seconds else None,
            )
        )
    runs.sort(key=lambda run: run.video_name)
    # Weighted by frames and plates, not a mean of per-video means: a tiny run must not dominate the average.
    track_seconds = sum((job.timings or {}).get("detection_and_tracking_s") or 0.0 for job, _ in rows)
    frames_total = sum(job.frames_processed or 0 for job, _ in rows)
    ocr_seconds = sum((job.timings or {}).get("ocr_s") or 0.0 for job, _ in rows)
    plates_total = sum(job.plates_examined or 0 for job, _ in rows)
    return Analytics(
        scope="video" if video_id is not None else "all",
        video_id=video_id,
        summary=metrics.summary(session, video_id),
        by_class=metrics.category_breakdown(session, video_id),
        by_status=metrics.validation_breakdown(session, video_id),
        detections_over_time=metrics.detections_over_time(session, video_id) if video_id is not None else [],
        confidence_distribution=distribution,
        runs=runs,
        average_detect_track_ms_per_frame=round(1000 * track_seconds / frames_total, 2) if frames_total else None,
        average_ocr_ms_per_plate=round(1000 * ocr_seconds / plates_total, 1) if plates_total else None,
    )
