"""The demonstration registry: FICTIONAL vehicle records, matched by registration number.

No real registration database is consulted, ever. Every record here was generated for the
demonstration and every screen that shows one must say so.

A number matches a record exactly, or is a "possible match" when a record is one character away
(one substitution, insertion or deletion: the 0/O, 8/B, 1/I misreads). A possible match is shown
in amber with the record and the differing character named, and is never counted as a Match.
Only confirmed numbers are looked up (the user's decision, 2026-11-07).

Records can belong to a named list and carry an operator's description (Axis item 5): added
from the dashboard for a recognised number, edited, or imported from a CSV. `note` stays the
provenance ("Added from the dashboard by … on …; fictional.").
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tracko_anpr.db.models import DemoRegistryEntry
from tracko_anpr.pipeline.validation import describe_difference, edit_distance, is_valid_plate, normalize

DISCLAIMER = "Demonstration data only. These records are fictional; no real registration database is consulted."
VEHICLE_TYPES = ("Car", "Motorcycle", "Bus", "Truck")
IMPORT_COLUMNS = (
    "registration_number",
    "owner_name",
    "vehicle_description",
    "vehicle_type",
    "colour",
    "registered_at",
    "valid_until",
    "description",
    "list_name",
)
IMPORT_TEMPLATE = (
    ",".join(IMPORT_COLUMNS) + "\n"
    "KL07AB1234,A. Demo,Maruti Suzuki Swift,Car,White,Ernakulam RTO,2028-12-31,visitor pass until Friday,Visitors\n"
)
PLACEHOLDER = "—"


class RegistryError(ValueError):
    """The record cannot be written; the message is for the operator."""


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
    """Provenance: who or what made the record."""
    fictional: bool = True
    description: str | None = None
    """An operator's free text."""
    list_name: str | None = None
    """The named list the record is in, if any."""


@dataclass(frozen=True)
class ListSummary:
    name: str
    count: int


@dataclass(frozen=True)
class ImportOutcome:
    created: int
    updated: int
    skipped: list[tuple[int, str]]
    """(CSV line number, reason) for every row that was not taken."""


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
        description=entry.description,
        list_name=entry.list_name,
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


def list_entries(
    session: Session, search: str | None = None, limit: int = 500, list_name: str | None = None
) -> list[RegistryRecord]:
    query = select(DemoRegistryEntry).order_by(DemoRegistryEntry.registration_number).limit(limit)
    if search:
        query = query.where(DemoRegistryEntry.registration_number.contains(search.upper().replace(" ", "")))
    if list_name:
        query = query.where(DemoRegistryEntry.list_name == list_name)
    return [_record(entry) for entry in session.scalars(query).all()]


def lists(session: Session) -> list[tuple[str, int]]:
    """Every list name in use with how many records it holds, alphabetically."""
    rows = session.execute(
        select(DemoRegistryEntry.list_name, func.count(DemoRegistryEntry.id))
        .where(DemoRegistryEntry.list_name.is_not(None))
        .group_by(DemoRegistryEntry.list_name)
        .order_by(DemoRegistryEntry.list_name)
    ).all()
    return [(name, int(count)) for name, count in rows]


def _clean_number(text: str | None) -> str:
    number = normalize(text or "")
    if not is_valid_plate(number):
        raise RegistryError(f"'{(text or '').strip()}' is not a valid Indian registration number.")
    return number


def _stamp(how: str, who: str) -> str:
    return f"{how} by {who.strip() or 'an operator'} on {date.today().isoformat()}; fictional."


def _new_entry(number: str, vehicle_type: str | None, note: str) -> DemoRegistryEntry:
    return DemoRegistryEntry(
        registration_number=number,
        owner_name="(added from the dashboard)",
        vehicle_description=PLACEHOLDER,
        vehicle_type=vehicle_type if vehicle_type in VEHICLE_TYPES else "Car",
        colour=PLACEHOLDER,
        registered_at=PLACEHOLDER,
        valid_until=date.today() + timedelta(days=365),
        note=note,
    )


def add_to_list(
    session: Session,
    number: str | None,
    list_name: str | None,
    description: str = "",
    vehicle_type: str | None = None,
    added_by: str = "",
) -> RegistryRecord:
    """Put a number in a named list: an existing record is labelled, a missing one is created (fictional)."""
    number = _clean_number(number)
    name = (list_name or "").strip()[:40]
    if not name:
        raise RegistryError("Give the list a name.")
    entry = session.scalar(select(DemoRegistryEntry).where(DemoRegistryEntry.registration_number == number))
    if entry is None:
        entry = _new_entry(number, vehicle_type, _stamp("Added from the dashboard", added_by))
        session.add(entry)
    entry.list_name = name
    entry.description = (description or "").strip()[:200] or None
    session.flush()
    session.refresh(entry)
    return _record(entry)


def update_record(
    session: Session, record_id: int, description: str | None = None, list_name: str | None = None
) -> RegistryRecord | None:
    """Change a record's description and/or list (an empty list name removes it). None when it does not exist."""
    entry = session.get(DemoRegistryEntry, record_id)
    if entry is None:
        return None
    if description is not None:
        entry.description = description.strip()[:200] or None
    if list_name is not None:
        entry.list_name = list_name.strip()[:40] or None
    session.flush()
    return _record(entry)


def remove_from_list(session: Session, record_id: int) -> RegistryRecord | None:
    return update_record(session, record_id, list_name="")


def import_csv(session: Session, text: str, filename: str = "upload.csv", added_by: str = "") -> ImportOutcome:
    """Create or update fictional records from a CSV with the IMPORT_COLUMNS header (only the number is required).

    An existing number is updated for the fields the row gives; an invalid number or date skips the row with
    the reason; an unknown vehicle type becomes "Car".
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    fields = [name.strip() for name in (reader.fieldnames or [])]
    if "registration_number" not in fields:
        raise RegistryError(
            "The CSV needs a header line with at least registration_number; the other columns are "
            + ", ".join(IMPORT_COLUMNS[1:])
            + ". Download the template for an example."
        )
    created = updated = 0
    skipped: list[tuple[int, str]] = []
    for line, raw in enumerate(reader, start=2):
        row = {(key or "").strip(): (value or "").strip() for key, value in raw.items()}
        try:
            number = _clean_number(row.get("registration_number"))
            valid_until = date.fromisoformat(row["valid_until"]) if row.get("valid_until") else None
        except RegistryError as error:
            skipped.append((line, str(error)))
            continue
        except ValueError:
            skipped.append((line, f"valid_until '{row.get('valid_until')}' is not a date (YYYY-MM-DD)"))
            continue
        entry = session.scalar(select(DemoRegistryEntry).where(DemoRegistryEntry.registration_number == number))
        if entry is None:
            entry = _new_entry(number, row.get("vehicle_type"), _stamp(f"Imported from {filename}", added_by))
            session.add(entry)
            created += 1
        else:
            updated += 1
        for column in ("owner_name", "vehicle_description", "colour", "registered_at"):
            if row.get(column):
                setattr(entry, column, row[column][:100])
        if row.get("vehicle_type") in VEHICLE_TYPES:
            entry.vehicle_type = row["vehicle_type"]
        if valid_until is not None:
            entry.valid_until = valid_until
        if row.get("description"):
            entry.description = row["description"][:200]
        if row.get("list_name"):
            entry.list_name = row["list_name"][:40]
    session.flush()
    return ImportOutcome(created, updated, skipped)


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
