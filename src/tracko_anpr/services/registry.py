"""The demonstration registry: FICTIONAL vehicle records, matched by registration number.

No real registration database is consulted, ever. Every record here was generated for the
demonstration and every screen that shows one must say so.

A number matches a record exactly, or is a "possible match" when a record is one character away
(one substitution, insertion or deletion: the 0/O, 8/B, 1/I misreads). A possible match is shown
in amber with the record and the differing character named, and is never counted as a Match.
Only confirmed numbers are looked up (the user's decision, 2026-11-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracko_anpr.db.models import DemoRegistryEntry
from tracko_anpr.pipeline.validation import describe_difference, edit_distance, normalize

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


@dataclass(frozen=True)
class RegistryMatch:
    """A record for a recognised number: exact, or one character away ("possible", never asserted)."""

    record: RegistryRecord
    exact: bool
    distance: int
    difference: str
    """For a possible match: which character differs, in words."""
    others: int = 0
    """How many more records were also one character away."""

    @property
    def possible(self) -> bool:
        return not self.exact

    @property
    def kind(self) -> str:
        return "exact" if self.exact else "possible"


@dataclass(frozen=True)
class RegistryLookup:
    """The API's answer for one number."""

    disclaimer: str
    match: bool
    possible: bool
    distance: int | None
    difference: str | None
    record: RegistryRecord | None


@dataclass(frozen=True)
class RegistryList:
    disclaimer: str
    entries: list[RegistryRecord]


def list_entries(session: Session, search: str | None = None, limit: int = 500) -> list[RegistryRecord]:
    query = select(DemoRegistryEntry).order_by(DemoRegistryEntry.registration_number).limit(limit)
    if search:
        query = query.where(DemoRegistryEntry.registration_number.contains(search.upper().replace(" ", "")))
    return [_record(entry) for entry in session.scalars(query).all()]


def _exact(entry: DemoRegistryEntry) -> RegistryMatch:
    return RegistryMatch(_record(entry), True, 0, "")


def _near_matches(session: Session, numbers: set[str]) -> dict[str, RegistryMatch]:
    """For numbers with no exact record: the record one character away (a substitution first, then the lowest number).

    The registry is tens of rows, so every number is compared in Python; one query, no index needed.
    """
    if not numbers:
        return {}
    entries = session.scalars(select(DemoRegistryEntry).order_by(DemoRegistryEntry.registration_number)).all()
    found: dict[str, RegistryMatch] = {}
    for number in numbers:
        near = [entry for entry in entries if edit_distance(number, entry.registration_number) == 1]
        if not near:
            continue
        near.sort(key=lambda entry: (len(entry.registration_number) != len(number), entry.registration_number))
        best = near[0]
        difference = describe_difference(number, best.registration_number)
        found[number] = RegistryMatch(_record(best), False, 1, difference, len(near) - 1)
    return found


def lookup(session: Session, registration_number: str | None) -> RegistryMatch | None:
    """The record for a number: exact, or one character away as a possible match; None is a "No Match"."""
    number = normalize(registration_number or "")
    if not number:
        return None
    entry = session.scalar(select(DemoRegistryEntry).where(DemoRegistryEntry.registration_number == number))
    if entry is not None:
        return _exact(entry)
    return _near_matches(session, {number}).get(number)


def lookup_many(session: Session, numbers: list[str | None]) -> dict[str, RegistryMatch]:
    """Matches for all the given numbers at once, keyed by (normalised) number; exact ones first."""
    wanted = {normalize(number) for number in numbers if number} - {""}
    if not wanted:
        return {}
    entries = session.scalars(select(DemoRegistryEntry).where(DemoRegistryEntry.registration_number.in_(wanted))).all()
    found = {entry.registration_number: _exact(entry) for entry in entries}
    found.update(_near_matches(session, wanted - set(found)))
    return found


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
    match: RegistryMatch | None

    @property
    def exact(self) -> bool:
        return self.match is not None and self.match.exact

    @property
    def possible(self) -> bool:
        return self.match is not None and self.match.possible

    @property
    def record(self) -> RegistryRecord | None:
        return self.match.record if self.match is not None else None


def recognized_numbers(session: Session, search: str | None = None) -> list[RecognizedNumber]:
    """Every confirmed number across the processed videos with its Match / Possible match / No match status."""
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
