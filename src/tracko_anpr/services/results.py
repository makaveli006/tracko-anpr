"""Results of processing: a video's figures, its detections, one detection in full, and the history."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from tracko_anpr.db import metrics
from tracko_anpr.db.metrics import Detection, Summary, approach_filter, latest_completed_jobs
from tracko_anpr.db.models import PlateObservation, ProcessingJob, RecognitionEvent, VehicleTrack, Video
from tracko_anpr.pipeline.direction import direction_label
from tracko_anpr.pipeline.validation import CONFIRMED, ValidationRules, correct, normalize
from tracko_anpr.services import corrections, registry
from tracko_anpr.services.corrections import Correction
from tracko_anpr.services.registry import RegistryMatch

RULES = ValidationRules()
"""The pipeline's frozen thresholds, used to place the 'read' and 'confirmed' events on a track's timeline."""


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
    detections_by_direction: list[tuple[int, int, int, int]]
    """Per bucket: start, towards the camera, away from it, undetermined; they add up to `detections_over_time`."""
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
        detections_by_direction=metrics.detections_over_time_by_direction(session, video_id),
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
    """One line of a detections table, with its fictional registry match and its operator correction, if any.

    `detection` is always the system's result; `correction` is what a person changed it to.
    """

    detection: Detection
    registry_match: RegistryMatch | None
    """Exact, or one character away ("possible", never asserted); only for confirmed numbers."""
    correction: Correction | None = None


def with_registry(session: Session, rows: list[Detection]) -> list[DetectionRow]:
    """Attach the registry match (by the system's confirmed number) and the current correction to each row."""
    matches = registry.lookup_many(session, [row.registration_number for row in rows if row.status == "confirmed"])
    corrected = corrections.current_corrections(session, [row.track_pk for row in rows])
    return [
        DetectionRow(
            row,
            matches.get(row.registration_number) if row.status == "confirmed" else None,
            corrected.get(row.track_pk),
        )
        for row in rows
    ]


def video_detections(
    session: Session, video_id: int, limit: int | None = None, newest_first: bool = True
) -> list[DetectionRow]:
    """A video's counted vehicles, newest first for the Recent Detections table, oldest first for a timeline."""
    return with_registry(session, metrics.detections(session, video_id, limit=limit, newest_first=newest_first))


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
class Event:
    """One step in a vehicle's life on the video, in the manner of a New / Update / Lost event stream.

    `time_s` and `frame` are video time; a correction happens at a wall-clock moment instead (`at`).
    """

    kind: str
    """new | read | confirmed | corrected | lost"""
    time_s: float | None
    frame: int | None
    text: str
    at: datetime | None = None


def lifecycle(
    track: VehicleTrack, event: RecognitionEvent, observations: list[PlateObservation], made: list[Correction]
) -> list[Event]:
    """Reconstruct the events from what is stored: nothing is recorded at processing time beyond the rows.

    - new: the track's first frame.
    - read: the first confident reading, then every later reading with a different text (the "updates").
    - confirmed: the observation at which the agreeing readings of the final number reached the
      validation rules' minimum, with one of them confident enough; only for confirmed tracks.
    - lost: the last frame, with the travel direction.
    - corrected: each operator correction, oldest first, at its wall-clock time.
    """
    direction = direction_label(track.approach, track.sideways)
    events = [Event("new", track.first_seen_s, track.first_frame, f"First seen · {track.vehicle_type}")]
    seen: set[str] = set()
    agreeing, best = 0, 0.0
    confirmed_at: Event | None = None
    number = event.registration_number if event.status == CONFIRMED else None
    confirmed_text = f"Number confirmed {number} ({event.confidence:.2f})"
    for o in observations:
        if not o.text or o.unreadable or o.ocr_confidence < RULES.min_reading_confidence:
            continue
        if o.text not in seen:
            seen.add(o.text)
            events.append(Event("read", o.time_s, o.frame, f"Read as {o.text} ({o.ocr_confidence:.2f})"))
        if number is not None and confirmed_at is None and _same_number(o.text, number):
            agreeing, best = agreeing + 1, max(best, o.ocr_confidence)
            if agreeing >= RULES.min_observations and best >= RULES.confirm_confidence:
                confirmed_at = Event("confirmed", o.time_s, o.frame, confirmed_text)
    if number is not None and confirmed_at is None:  # agreed through look-alike correction only: place it at the end
        confirmed_at = Event("confirmed", track.last_seen_s, track.last_frame, confirmed_text)
    if confirmed_at is not None:
        events.append(confirmed_at)
    events.append(Event("lost", track.last_seen_s, track.last_frame, f"Last seen · {direction}"))
    events.sort(key=lambda e: (e.frame if e.frame is not None else 0, _KIND_ORDER.get(e.kind, 9)))
    for c in reversed(made):  # oldest first
        changed = " / ".join(filter(None, [c.corrected_number, c.corrected_type]))
        who = f" by {c.corrected_by}" if c.corrected_by else ""
        events.append(Event("corrected", None, None, f"Corrected to {changed}{who}", at=c.created_at))
    return events


_KIND_ORDER = {"new": 0, "read": 1, "confirmed": 2, "lost": 3}


def _same_number(text: str, number: str) -> bool:
    """A reading counts for the final number as written or after the validator's look-alike correction."""
    if text == number:
        return True
    corrected = correct(normalize(text))
    return corrected is not None and corrected[0] == number


@dataclass(frozen=True)
class DetectionDetail:
    detection: Detection
    registry_match: RegistryMatch | None
    frames_seen: int
    first_frame: int
    last_frame: int
    countable: bool
    camera_car: bool
    same_vehicle_as: int | None
    share: float
    observations: list[Observation]
    """Every plate examined for this track, in frame order: the multi-frame evidence."""
    correction: Correction | None = None
    """The current operator correction, if any; the system's result above is unchanged by it."""
    corrections: list[Correction] = field(default_factory=list)
    """Every correction made to this track, newest first."""
    events: list[Event] = field(default_factory=list)
    """The track's life on the video: first seen, readings, confirmed, corrected, last seen (see `lifecycle`)."""


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
    made = corrections.history(session, track.id)
    return DetectionDetail(
        correction=made[0] if made else None,
        corrections=made,
        events=lifecycle(track, event, list(observations), made),
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
    "direction": (VehicleTrack.approach, VehicleTrack.sideways),
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


def _history_query(
    video_id: int | None,
    status: str | None,
    vehicle_type: str | None,
    search: str | None,
    approach: str | None = None,
) -> Select:
    query = approach_filter(
        select(VehicleTrack, RecognitionEvent, Video.name)
        .join(RecognitionEvent, RecognitionEvent.track_pk == VehicleTrack.id)
        .join(Video, Video.id == VehicleTrack.video_id)
        .where(VehicleTrack.job_id.in_(latest_completed_jobs(video_id)), VehicleTrack.counts_as_vehicle),
        approach,
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
    approach: str | None = None,
) -> HistoryPage:
    """Counted vehicles across all processed videos (or one), filtered, sorted and paged."""
    query = _history_query(video_id, status, vehicle_type, search, approach)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    columns = SORTABLE.get(sort, SORTABLE["time"])
    ordered = query.order_by(*(c.desc() if descending else c.asc() for c in columns), VehicleTrack.id)
    rows = session.execute(ordered.offset(offset).limit(limit)).all()
    detections = [_detection(track, event, name) for track, event, name in rows]
    return HistoryPage(with_registry(session, detections), int(total), offset, limit)


def export_history_csv(session: Session, **filters) -> str:
    """The same rows as `detection_history`, all of them, as CSV text."""
    query = _history_query(
        filters.get("video_id"),
        filters.get("status"),
        filters.get("vehicle_type"),
        filters.get("search"),
        filters.get("approach"),
    ).order_by(Video.name, VehicleTrack.first_seen_s, VehicleTrack.track_id)
    rows = with_registry(session, [_detection(t, e, n) for t, e, n in session.execute(query).all()])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["video", "track", "vehicle_type", "first_seen_s", "last_seen_s", "direction", "registration_number"]
        + ["status", "confidence", "agreeing_frames", "readings", "reason", "demo_registry_match"]
        + ["demo_registry_possible"]
        + ["corrected_number", "corrected_type", "corrected_by", "corrected_at"]
    )
    for row in rows:
        d, c = row.detection, row.correction
        corrected = (
            [c.corrected_number or "", c.corrected_type or "", c.corrected_by, c.created_at.isoformat()]
            if c
            else ["", "", "", ""]
        )
        writer.writerow(
            [d.video_name, f"T{d.track_id}", d.vehicle_type, d.first_seen_s, d.last_seen_s, d.direction_label]
            + [d.registration_number or "", d.status, f"{d.confidence:.4f}", d.support, d.readings, d.reason]
            + [m.record.owner_name if (m := row.registry_match) and m.exact else ""]
            + [m.record.registration_number if m and m.possible else ""]
            + corrected
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
        approach=track.approach,
        sideways=track.sideways,
    )
