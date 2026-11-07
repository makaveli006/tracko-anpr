"""The demonstration registry: FICTIONAL vehicle records, matched by registration number.

No real registration database is consulted, ever. Every record here was generated for the
demonstration and every screen that shows one must say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracko_anpr.db.models import DemoRegistryEntry

DISCLAIMER = "Demonstration data only. These records are fictional; no real registration database is consulted."


@dataclass(frozen=True)
class RegistryRecord:
    id: int
    registration_number: str
    owner_name: str
    vehicle_description: str
    vehicle_type: str
    colour: str
    registered_at: str
    valid_until: date
    note: str
    fictional: bool = True


def _record(entry: DemoRegistryEntry) -> RegistryRecord:
    return RegistryRecord(
        id=entry.id,
        registration_number=entry.registration_number,
        owner_name=entry.owner_name,
        vehicle_description=entry.vehicle_description,
        vehicle_type=entry.vehicle_type,
        colour=entry.colour,
        registered_at=entry.registered_at,
        valid_until=entry.valid_until,
        note=entry.note,
    )


def list_entries(session: Session, search: str | None = None, limit: int = 500) -> list[RegistryRecord]:
    query = select(DemoRegistryEntry).order_by(DemoRegistryEntry.registration_number).limit(limit)
    if search:
        query = query.where(DemoRegistryEntry.registration_number.contains(search.upper().replace(" ", "")))
    return [_record(entry) for entry in session.scalars(query).all()]


def lookup(session: Session, registration_number: str | None) -> RegistryRecord | None:
    """The fictional record for a number, or None: a "No Match"."""
    if not registration_number:
        return None
    entry = session.scalar(
        select(DemoRegistryEntry).where(DemoRegistryEntry.registration_number == registration_number.upper())
    )
    return None if entry is None else _record(entry)


def lookup_many(session: Session, numbers: list[str | None]) -> dict[str, RegistryRecord]:
    """Records for all the given numbers at once, keyed by number."""
    wanted = {number.upper() for number in numbers if number}
    if not wanted:
        return {}
    entries = session.scalars(select(DemoRegistryEntry).where(DemoRegistryEntry.registration_number.in_(wanted))).all()
    return {entry.registration_number: _record(entry) for entry in entries}


def count(session: Session) -> int:
    from sqlalchemy import func

    return int(session.scalar(select(func.count()).select_from(DemoRegistryEntry)) or 0)


@dataclass(frozen=True)
class RecognizedNumber:
    """A number the pipeline confirmed, and whether the fictional registry knows it."""

    registration_number: str
    vehicle_type: str
    videos: list[str]
    sightings: int
    """Counted vehicles that carry this number across the latest runs."""
    best_confidence: float
    record: RegistryRecord | None

    @property
    def match(self) -> bool:
        return self.record is not None


def recognized_numbers(session: Session, search: str | None = None) -> list[RecognizedNumber]:
    """Every confirmed number across the processed videos with its Match / No Match status."""
    from tracko_anpr.db.metrics import latest_completed_jobs
    from tracko_anpr.db.models import RecognitionEvent, VehicleTrack, Video

    rows = session.execute(
        select(RecognitionEvent.registration_number, VehicleTrack.vehicle_type, Video.name, RecognitionEvent.confidence)
        .join(VehicleTrack, VehicleTrack.id == RecognitionEvent.track_pk)
        .join(Video, Video.id == VehicleTrack.video_id)
        .where(
            RecognitionEvent.job_id.in_(latest_completed_jobs()),
            RecognitionEvent.status == "confirmed",
            VehicleTrack.counts_as_vehicle,
        )
        .order_by(RecognitionEvent.registration_number)
    ).all()
    grouped: dict[str, dict] = {}
    for number, vehicle_type, video_name, confidence in rows:
        if search and search.upper().replace(" ", "") not in number:
            continue
        item = grouped.setdefault(number, {"type": vehicle_type, "videos": [], "count": 0, "best": 0.0})
        if video_name not in item["videos"]:
            item["videos"].append(video_name)
        item["count"] += 1
        item["best"] = max(item["best"], confidence)
    records = lookup_many(session, list(grouped))
    return [
        RecognizedNumber(number, item["type"], item["videos"], item["count"], item["best"], records.get(number))
        for number, item in grouped.items()
    ]
