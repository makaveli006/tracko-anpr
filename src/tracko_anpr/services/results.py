"""Results of processing: a video's figures, its detections, one detection in full, and the history."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from tracko_anpr.db import metrics
from tracko_anpr.db.metrics import Detection, Summary, latest_completed_jobs
from tracko_anpr.db.models import PlateObservation, ProcessingJob, RecognitionEvent, VehicleTrack, Video
from tracko_anpr.services import registry
from tracko_anpr.services.registry import RegistryRecord


@dataclass(frozen=True)
class VideoResults:
    """Everything the Overview and Video Analysis pages need for one video."""

    video_id: int
    video_name: str
    job_id: int | None
    """The latest completed job; None when the video has not been processed yet."""
    processed_at: datetime | None
    summary: Summary
    by_class: dict[str, int]
    by_status: dict[str, int]
    detections_over_time: list[tuple[int, int]]
    timings: dict | None
    memory: dict | None
    settings: dict | None
    annotated_video_path: str | None
    results_path: str | None
    detections_path: str | None
    plates_path: str | None


def video_results(session: Session, video_id: int) -> VideoResults | None:
    video = session.get(Video, video_id)
    if video is None:
        return None
    job_id = session.scalar(latest_completed_jobs(video_id))
    job = session.get(ProcessingJob, job_id) if job_id is not None else None
    return VideoResults(
        video_id=video.id,
        video_name=video.name,
        job_id=job_id,
        processed_at=job.finished_at if job else None,
        summary=metrics.summary(session, video_id),
        by_class=metrics.category_breakdown(session, video_id),
        by_status=metrics.validation_breakdown(session, video_id),
        detections_over_time=metrics.detections_over_time(session, video_id),
        timings=job.timings if job else None,
        memory=job.memory if job else None,
        settings=job.settings if job else None,
        annotated_video_path=job.annotated_video_path if job else None,
        results_path=job.results_path if job else None,
        detections_path=job.detections_path if job else None,
        plates_path=job.plates_path if job else None,
    )


@dataclass(frozen=True)
class DetectionRow:
    """One line of a detections table, with its fictional registry match if any."""

    detection: Detection
    registry_match: RegistryRecord | None


def with_registry(session: Session, rows: list[Detection]) -> list[DetectionRow]:
    matches = registry.lookup_many(session, [row.registration_number for row in rows if row.status == "confirmed"])
    return [
        DetectionRow(row, matches.get(row.registration_number) if row.status == "confirmed" else None) for row in rows
    ]


def video_detections(session: Session, video_id: int, limit: int | None = None) -> list[DetectionRow]:
    """A video's counted vehicles, newest first, for the Recent Detections table."""
    return with_registry(session, metrics.detections(session, video_id, limit=limit))


@dataclass(frozen=True)
class Observation:
    frame: int
    time_s: float
    box: tuple[float, float, float, float]
    detector_confidence: float
    text: str
    ocr_confidence: float
    unreadable: bool
    second_decoder_text: str
    found_in_track: int
    crop_path: str | None


@dataclass(frozen=True)
class DetectionDetail:
    detection: Detection
    registry_match: RegistryRecord | None
    frames_seen: int
    first_frame: int
    last_frame: int
    countable: bool
    camera_car: bool
    same_vehicle_as: int | None
    share: float
    observations: list[Observation]
    """Every plate examined for this track, in frame order: the multi-frame evidence."""


def detection_detail(session: Session, track_pk: int) -> DetectionDetail | None:
    track = session.get(VehicleTrack, track_pk)
    if track is None or track.recognition is None:
        return None
    event = track.recognition
    video_name = session.scalar(select(Video.name).where(Video.id == track.video_id))
    detection = _detection(track, event, video_name)
    observations = session.scalars(
        select(PlateObservation).where(PlateObservation.track_pk == track.id).order_by(PlateObservation.frame)
    ).all()
    return DetectionDetail(
        detection=detection,
        registry_match=registry.lookup(session, event.registration_number) if event.status == "confirmed" else None,
        frames_seen=track.frames_seen,
        first_frame=track.first_frame,
        last_frame=track.last_frame,
        countable=track.countable,
        camera_car=track.camera_car,
        same_vehicle_as=track.same_vehicle_as,
        share=event.share,
        observations=[
            Observation(
                frame=o.frame,
                time_s=o.time_s,
                box=(o.x1, o.y1, o.x2, o.y2),
                detector_confidence=o.detector_confidence,
                text=o.text,
                ocr_confidence=o.ocr_confidence,
                unreadable=o.unreadable,
                second_decoder_text=o.second_decoder_text,
                found_in_track=o.found_in_track,
                crop_path=o.crop_path,
            )
            for o in observations
        ],
    )


# --- Detection History: every video, searchable -------------------------------------------------

SORTABLE = {
    "time": (VehicleTrack.video_id, VehicleTrack.first_seen_s),
    "video": (Video.name, VehicleTrack.first_seen_s),
    "track": (VehicleTrack.track_id,),
    "vehicle_type": (VehicleTrack.vehicle_type,),
    "registration_number": (RecognitionEvent.registration_number,),
    "confidence": (RecognitionEvent.confidence,),
    "status": (RecognitionEvent.status,),
}


@dataclass(frozen=True)
class HistoryPage:
    rows: list[DetectionRow]
    total: int
    offset: int
    limit: int


def _history_query(video_id: int | None, status: str | None, vehicle_type: str | None, search: str | None) -> Select:
    query = (
        select(VehicleTrack, RecognitionEvent, Video.name)
        .join(RecognitionEvent, RecognitionEvent.track_pk == VehicleTrack.id)
        .join(Video, Video.id == VehicleTrack.video_id)
        .where(VehicleTrack.job_id.in_(latest_completed_jobs(video_id)), VehicleTrack.counts_as_vehicle)
    )
    if status:
        query = query.where(RecognitionEvent.status == status)
    if vehicle_type:
        query = query.where(VehicleTrack.vehicle_type == vehicle_type)
    if search:
        query = query.where(RecognitionEvent.registration_number.contains(search.upper().replace(" ", "")))
    return query


def detection_history(
    session: Session,
    video_id: int | None = None,
    status: str | None = None,
    vehicle_type: str | None = None,
    search: str | None = None,
    sort: str = "time",
    descending: bool = True,
    offset: int = 0,
    limit: int = 50,
) -> HistoryPage:
    """Counted vehicles across all processed videos (or one), filtered, sorted and paged."""
    query = _history_query(video_id, status, vehicle_type, search)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    columns = SORTABLE.get(sort, SORTABLE["time"])
    ordered = query.order_by(*(c.desc() if descending else c.asc() for c in columns), VehicleTrack.id)
    rows = session.execute(ordered.offset(offset).limit(limit)).all()
    detections = [_detection(track, event, name) for track, event, name in rows]
    return HistoryPage(with_registry(session, detections), int(total), offset, limit)


def export_history_csv(session: Session, **filters) -> str:
    """The same rows as `detection_history`, all of them, as CSV text."""
    query = _history_query(
        filters.get("video_id"), filters.get("status"), filters.get("vehicle_type"), filters.get("search")
    ).order_by(Video.name, VehicleTrack.first_seen_s, VehicleTrack.track_id)
    rows = with_registry(session, [_detection(t, e, n) for t, e, n in session.execute(query).all()])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["video", "track", "vehicle_type", "first_seen_s", "last_seen_s", "registration_number", "status"]
        + ["confidence", "agreeing_frames", "readings", "reason", "demo_registry_match"]
    )
    for row in rows:
        d = row.detection
        writer.writerow(
            [d.video_name, f"T{d.track_id}", d.vehicle_type, d.first_seen_s, d.last_seen_s, d.registration_number or ""]
            + [d.status, f"{d.confidence:.4f}", d.support, d.readings, d.reason]
            + [row.registry_match.owner_name if row.registry_match else ""]
        )
    return buffer.getvalue()


def _detection(track: VehicleTrack, event: RecognitionEvent, video_name: str) -> Detection:
    return Detection(
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
