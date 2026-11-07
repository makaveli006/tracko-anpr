"""The dashboard's figures, defined once as queries.

Every figure is measured over each video's latest completed job ("a re-processed video shows
its latest completed job"), either for one video or across all of them:

    Total Vehicles        tracks that count as vehicles (countable and not a repeat)
    Unique Tracks         every track the tracker produced
    Recognized Plates     counted vehicles whose number is confirmed
    Recognition coverage  Recognized Plates ÷ Total Vehicles. Coverage, not accuracy.
    Videos Processed      videos with at least one completed job
    Avg. Processing Time  mean wall-clock time of those latest jobs
    Detections Over Time  new vehicles per 10-second bucket of video time, each vehicle
                          counted once where it is first seen, so the buckets add up to
                          Total Vehicles
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from tracko_anpr.db.models import COMPLETED, ProcessingJob, RecognitionEvent, VehicleTrack, Video
from tracko_anpr.pipeline.tracking import VEHICLE_CLASSES
from tracko_anpr.pipeline.validation import CONFIRMED, NOT_DETECTED, UNCONFIRMED

BUCKET_SECONDS = 10


def latest_completed_jobs(video_id: int | None = None) -> Select:
    """Ids of each video's most recently finished job (one video's, or every video's)."""
    ranked = select(
        ProcessingJob.id.label("job_id"),
        func.row_number()
        .over(partition_by=ProcessingJob.video_id, order_by=(ProcessingJob.finished_at.desc(), ProcessingJob.id.desc()))
        .label("rank"),
    ).where(ProcessingJob.status == COMPLETED)
    if video_id is not None:
        ranked = ranked.where(ProcessingJob.video_id == video_id)
    ranked = ranked.subquery()
    return select(ranked.c.job_id).where(ranked.c.rank == 1)


@dataclass(frozen=True)
class Summary:
    total_vehicles: int
    unique_tracks: int
    confirmed_plates: int
    recognition_coverage: float | None
    """Confirmed ÷ total vehicles; None when there are no vehicles. Not accuracy."""
    videos_processed: int
    average_processing_seconds: float | None
    last_run_at: datetime | None


def summary(session: Session, video_id: int | None = None) -> Summary:
    """The five Overview cards and the header's "last run", for one video or all."""
    jobs = latest_completed_jobs(video_id)
    tracks = session.execute(
        select(
            func.count(VehicleTrack.id),
            func.coalesce(func.sum(case((VehicleTrack.counts_as_vehicle, 1), else_=0)), 0),
        ).where(VehicleTrack.job_id.in_(jobs))
    ).one()
    unique_tracks, total_vehicles = int(tracks[0]), int(tracks[1])
    confirmed = session.scalar(
        select(func.count(RecognitionEvent.id))
        .join(VehicleTrack, VehicleTrack.id == RecognitionEvent.track_pk)
        .where(RecognitionEvent.job_id.in_(jobs), RecognitionEvent.status == CONFIRMED, VehicleTrack.counts_as_vehicle)
    )
    job_facts = session.execute(
        select(
            func.count(ProcessingJob.id),
            func.avg(ProcessingJob.processing_seconds),
            func.max(ProcessingJob.finished_at),
        ).where(ProcessingJob.id.in_(jobs))
    ).one()
    return Summary(
        total_vehicles=total_vehicles,
        unique_tracks=unique_tracks,
        confirmed_plates=int(confirmed or 0),
        recognition_coverage=round(confirmed / total_vehicles, 4) if total_vehicles else None,
        videos_processed=int(job_facts[0]),
        average_processing_seconds=float(job_facts[1]) if job_facts[1] is not None else None,
        last_run_at=job_facts[2],
    )


def category_breakdown(session: Session, video_id: int | None = None) -> dict[str, int]:
    """Counted vehicles by type, always listing all four classes."""
    rows = session.execute(
        select(VehicleTrack.vehicle_type, func.count(VehicleTrack.id))
        .where(VehicleTrack.job_id.in_(latest_completed_jobs(video_id)), VehicleTrack.counts_as_vehicle)
        .group_by(VehicleTrack.vehicle_type)
    ).all()
    counts = dict.fromkeys(VEHICLE_CLASSES.values(), 0)
    for vehicle_type, count in rows:
        counts[vehicle_type] = int(count)
    return counts


def validation_breakdown(session: Session, video_id: int | None = None) -> dict[str, int]:
    """Counted vehicles by plate status: confirmed, unconfirmed, not_detected."""
    rows = session.execute(
        select(RecognitionEvent.status, func.count(RecognitionEvent.id))
        .join(VehicleTrack, VehicleTrack.id == RecognitionEvent.track_pk)
        .where(RecognitionEvent.job_id.in_(latest_completed_jobs(video_id)), VehicleTrack.counts_as_vehicle)
        .group_by(RecognitionEvent.status)
    ).all()
    counts = dict.fromkeys((CONFIRMED, UNCONFIRMED, NOT_DETECTED), 0)
    for status, count in rows:
        counts[status] = int(count)
    return counts


def detections_over_time(
    session: Session, video_id: int, bucket_seconds: int = BUCKET_SECONDS
) -> list[tuple[int, int]]:
    """(bucket start in seconds, new vehicles first seen in that bucket) for one video, in order.

    Empty buckets are filled in up to the video's length so the chart's x-axis is continuous.
    """
    bucket = func.floor(VehicleTrack.first_seen_s / bucket_seconds)
    rows = session.execute(
        select(bucket, func.count(VehicleTrack.id))
        .where(VehicleTrack.job_id.in_(latest_completed_jobs(video_id)), VehicleTrack.counts_as_vehicle)
        .group_by(bucket)
        .order_by(bucket)
    ).all()
    counts = {int(index): int(count) for index, count in rows}
    duration = session.scalar(select(Video.duration_s).where(Video.id == video_id)) or 0.0
    last_bucket = max([int(duration // bucket_seconds), *counts.keys()]) if counts or duration else -1
    return [(index * bucket_seconds, counts.get(index, 0)) for index in range(last_bucket + 1)]


@dataclass(frozen=True)
class Detection:
    """One row of the detections tables: a counted vehicle and what was made of its plate."""

    video_id: int
    video_name: str
    job_id: int
    track_pk: int
    track_id: int
    vehicle_type: str
    detection_confidence: float
    first_seen_s: float
    last_seen_s: float
    status: str
    registration_number: str | None
    confidence: float
    support: int
    readings: int
    reason: str
    vehicle_crop_path: str | None
    plate_crop_path: str | None


def detections(
    session: Session,
    video_id: int | None = None,
    limit: int | None = None,
    newest_first: bool = True,
) -> list[Detection]:
    """Counted vehicles with their plate decision, for the Recent Detections table and Detection History."""
    query = (
        select(VehicleTrack, RecognitionEvent, Video.name)
        .join(RecognitionEvent, RecognitionEvent.track_pk == VehicleTrack.id)
        .join(Video, Video.id == VehicleTrack.video_id)
        .where(VehicleTrack.job_id.in_(latest_completed_jobs(video_id)), VehicleTrack.counts_as_vehicle)
    )
    order = (VehicleTrack.video_id, VehicleTrack.first_seen_s, VehicleTrack.track_id)
    query = query.order_by(*(column.desc() for column in order) if newest_first else order)
    if limit is not None:
        query = query.limit(limit)
    return [
        Detection(
            video_id=track.video_id,
            video_name=video_name,
            job_id=track.job_id,
            track_pk=track.id,
            track_id=track.track_id,
            vehicle_type=track.vehicle_type,
            detection_confidence=track.detection_confidence,
            first_seen_s=track.first_seen_s,
            last_seen_s=track.last_seen_s,
            status=event.status,
            registration_number=event.registration_number,
            confidence=event.confidence,
            support=event.support,
            readings=event.readings,
            reason=event.reason,
            vehicle_crop_path=track.vehicle_crop_path,
            plate_crop_path=event.plate_crop_path,
        )
        for track, event, video_name in session.execute(query).all()
    ]


def processing_durations(session: Session) -> list[tuple[str, float]]:
    """(video name, seconds) for each video's latest completed job, for the Analytics page."""
    rows = session.execute(
        select(Video.name, ProcessingJob.processing_seconds)
        .join(ProcessingJob, ProcessingJob.video_id == Video.id)
        .where(ProcessingJob.id.in_(latest_completed_jobs()))
        .order_by(Video.name)
    ).all()
    return [(name, float(seconds or 0.0)) for name, seconds in rows]
