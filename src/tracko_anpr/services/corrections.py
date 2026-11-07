"""Operators' corrections of recognised numbers and vehicle types.

A correction never changes the pipeline's own result: `recognition_events` and `vehicle_tracks`
keep what the system concluded, the dashboard's figures keep counting them, and the correction
is stored beside them in `plate_corrections`. The newest correction for a track is the current
one; older ones stay as history. Corrections are the human answers the accuracy procedure in
ARCHITECTURE.md needs ("true_number", "true_type"), so they export with the detections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tracko_anpr.db.metrics import latest_completed_jobs
from tracko_anpr.db.models import PlateCorrection, RecognitionEvent, VehicleTrack, Video
from tracko_anpr.pipeline.tracking import VEHICLE_CLASSES
from tracko_anpr.pipeline.validation import CONFIRMED, is_valid_plate, normalize

VEHICLE_TYPES = tuple(VEHICLE_CLASSES.values())


class CorrectionError(ValueError):
    """The correction cannot be saved; the message says why, in words for the operator."""


@dataclass(frozen=True)
class Correction:
    id: int
    track_pk: int
    video_id: int
    video_name: str
    track_id: int
    system_number: str | None
    system_status: str
    system_type: str
    corrected_number: str | None
    corrected_type: str | None
    corrected_by: str
    note: str
    created_at: datetime

    @property
    def number(self) -> str | None:
        """The number to show: the corrected one, else the system's."""
        return self.corrected_number or self.system_number

    @property
    def vehicle_type(self) -> str:
        return self.corrected_type or self.system_type


@dataclass(frozen=True)
class CorrectionSummary:
    corrections: int
    """Correction rows, history included."""
    tracks_corrected: int
    """Tracks with a current correction."""
    numbers_corrected: int
    types_corrected: int
    confirmed_numbers_changed: int
    """Tracks whose confirmed number an operator replaced: the ones that bear on reading accuracy."""
    confirmed_total: int


def _record(row: PlateCorrection, video_name: str, track_id: int) -> Correction:
    return Correction(
        id=row.id,
        track_pk=row.track_pk,
        video_id=row.video_id,
        video_name=video_name,
        track_id=track_id,
        system_number=row.system_number,
        system_status=row.system_status,
        system_type=row.system_type,
        corrected_number=row.corrected_number,
        corrected_type=row.corrected_type,
        corrected_by=row.corrected_by,
        note=row.note,
        created_at=row.created_at,
    )


def clean_number(text: str | None) -> str | None:
    """Normalise an operator's number and check its format; None for an empty field."""
    if text is None or not text.strip():
        return None
    number = normalize(text)
    if not is_valid_plate(number):
        raise CorrectionError(
            f"'{text.strip()}' is not a valid Indian registration number (for example KL07AB1234 or 22BH1234AB)."
        )
    return number


def save_correction(
    session: Session,
    track_pk: int,
    number: str | None,
    vehicle_type: str | None,
    corrected_by: str = "",
    note: str = "",
) -> Correction:
    """Record a correction of the number, the type, or both. Refuses what would change nothing."""
    track = session.get(VehicleTrack, track_pk)
    if track is None or track.recognition is None:
        raise CorrectionError("That detection is not in the database.")
    event: RecognitionEvent = track.recognition
    corrected_number = clean_number(number)
    corrected_type = (vehicle_type or "").strip() or None
    if corrected_type is not None and corrected_type not in VEHICLE_TYPES:
        raise CorrectionError(f"Vehicle type must be one of {', '.join(VEHICLE_TYPES)}.")
    if corrected_number == event.registration_number:
        corrected_number = None  # same as the system's: nothing to correct
    if corrected_type == track.vehicle_type:
        corrected_type = None
    if corrected_number is None and corrected_type is None:
        raise CorrectionError("Nothing to correct: that is already the system's result.")
    row = PlateCorrection(
        track_pk=track.id,
        job_id=track.job_id,
        video_id=track.video_id,
        system_number=event.registration_number,
        system_status=event.status,
        system_type=track.vehicle_type,
        corrected_number=corrected_number,
        corrected_type=corrected_type,
        corrected_by=(corrected_by or "").strip()[:100],
        note=(note or "").strip()[:2000],
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    video_name = session.scalar(select(Video.name).where(Video.id == track.video_id)) or ""
    return _record(row, video_name, track.track_id)


def history(session: Session, track_pk: int) -> list[Correction]:
    """Every correction of a track, newest first."""
    rows = session.execute(
        select(PlateCorrection, Video.name, VehicleTrack.track_id)
        .join(VehicleTrack, VehicleTrack.id == PlateCorrection.track_pk)
        .join(Video, Video.id == PlateCorrection.video_id)
        .where(PlateCorrection.track_pk == track_pk)
        .order_by(PlateCorrection.created_at.desc(), PlateCorrection.id.desc())
    ).all()
    return [_record(row, name, track_id) for row, name, track_id in rows]


def current_corrections(session: Session, track_pks: list[int]) -> dict[int, Correction]:
    """The newest correction of each given track, keyed by track_pk; tracks without one are absent."""
    if not track_pks:
        return {}
    rows = session.execute(
        select(PlateCorrection, Video.name, VehicleTrack.track_id)
        .join(VehicleTrack, VehicleTrack.id == PlateCorrection.track_pk)
        .join(Video, Video.id == PlateCorrection.video_id)
        .where(PlateCorrection.track_pk.in_(track_pks))
        .order_by(PlateCorrection.created_at.desc(), PlateCorrection.id.desc())
    ).all()
    current: dict[int, Correction] = {}
    for row, name, track_id in rows:
        current.setdefault(row.track_pk, _record(row, name, track_id))  # first seen is the newest
    return current


def undo_latest(session: Session, track_pk: int) -> bool:
    """Remove the newest correction of a track. False when there was none."""
    row = session.scalar(
        select(PlateCorrection)
        .where(PlateCorrection.track_pk == track_pk)
        .order_by(PlateCorrection.created_at.desc(), PlateCorrection.id.desc())
        .limit(1)
    )
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def list_corrections(session: Session, video_id: int | None = None) -> list[Correction]:
    """Current corrections across the latest runs (one per track), newest first."""
    query = (
        select(PlateCorrection, Video.name, VehicleTrack.track_id)
        .join(VehicleTrack, VehicleTrack.id == PlateCorrection.track_pk)
        .join(Video, Video.id == PlateCorrection.video_id)
        .where(PlateCorrection.job_id.in_(latest_completed_jobs(video_id)))
        .order_by(PlateCorrection.created_at.desc(), PlateCorrection.id.desc())
    )
    current: dict[int, Correction] = {}
    for row, name, track_id in session.execute(query).all():
        current.setdefault(row.track_pk, _record(row, name, track_id))
    return list(current.values())


def summary(session: Session, video_id: int | None = None) -> CorrectionSummary:
    """How much operators have corrected, over the latest runs. The figures elsewhere ignore corrections."""
    jobs = latest_completed_jobs(video_id)
    total = session.scalar(select(func.count(PlateCorrection.id)).where(PlateCorrection.job_id.in_(jobs))) or 0
    current = list_corrections(session, video_id)
    confirmed_total = session.scalar(
        select(func.count(RecognitionEvent.id))
        .join(VehicleTrack, VehicleTrack.id == RecognitionEvent.track_pk)
        .where(RecognitionEvent.job_id.in_(jobs), RecognitionEvent.status == CONFIRMED, VehicleTrack.counts_as_vehicle)
    )
    return CorrectionSummary(
        corrections=int(total),
        tracks_corrected=len(current),
        numbers_corrected=sum(1 for c in current if c.corrected_number),
        types_corrected=sum(1 for c in current if c.corrected_type),
        confirmed_numbers_changed=sum(1 for c in current if c.corrected_number and c.system_status == CONFIRMED),
        confirmed_total=int(confirmed_total or 0),
    )
