"""Generating the FICTIONAL demonstration registry.

Records are made up for a share of the registration numbers the pipeline confirmed in the
processed videos, plus a few numbers that appear in no video, so the demo shows both matches
and non-matches; and, for a share of the confirmed numbers that got no record, a near-miss
record one character away, so the "possible match" state shows too. Every field is invented:
names, vehicles, colours, offices and dates. No real
registration data is involved, and every screen that shows a record says so.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracko_anpr.db.metrics import latest_completed_jobs
from tracko_anpr.db.models import DemoRegistryEntry, RecognitionEvent, VehicleTrack
from tracko_anpr.pipeline.validation import CONFIRMED, is_valid_plate

NOTE = "Fictional record generated for the demonstration."
NEAR_NOTE = "Fictional near-miss record for the demonstration (one character from {number})."
LOOKALIKE_DIGIT = {"0": "8", "1": "7", "2": "7", "3": "8", "4": "1", "5": "6", "6": "5", "7": "1", "8": "3", "9": "0"}
LOOKALIKE_LETTER = {
    "A": "H", "B": "R", "C": "G", "D": "B", "E": "F", "F": "E", "G": "C", "H": "N", "J": "U", "K": "X",
    "L": "E", "M": "N", "N": "M", "P": "R", "Q": "D", "R": "P", "S": "B", "T": "Y", "U": "V", "V": "U",
    "W": "V", "X": "K", "Y": "T", "Z": "S",
}  # fmt: skip

FIRST_NAMES = (
    "Anand", "Priya", "Rahul", "Meera", "Suresh", "Lakshmi", "Vikram", "Anjali", "Arjun", "Divya",
    "Manoj", "Kavya", "Rajesh", "Sneha", "Nithin", "Pooja", "Sanjay", "Reshma", "Deepak", "Nisha",
)  # fmt: skip
LAST_NAMES = (
    "Nair", "Menon", "Pillai", "Kumar", "Varma", "Iyer", "Krishnan", "Thomas", "Joseph", "Reddy",
    "Sharma", "Patel", "Das", "Mathew", "Rao", "Gupta", "Singh", "Shetty", "Naik", "George",
)  # fmt: skip
VEHICLES = {
    "Car": (
        "Maruti Suzuki Swift",
        "Hyundai i20",
        "Tata Nexon",
        "Honda City",
        "Toyota Innova Crysta",
        "Kia Seltos",
        "Mahindra XUV700",
        "Maruti Suzuki Baleno",
    ),
    "Motorcycle": (
        "Honda Activa 6G",
        "TVS Jupiter",
        "Bajaj Pulsar 150",
        "Royal Enfield Classic 350",
        "Hero Splendor Plus",
        "Suzuki Access 125",
        "Yamaha FZ-S",
        "TVS Apache RTR 160",
    ),
    "Bus": ("Ashok Leyland Viking", "Tata Starbus", "Eicher Skyline Pro", "Volvo 9600"),
    "Truck": ("Tata 407", "Ashok Leyland Dost", "Mahindra Bolero Pik-Up", "Eicher Pro 2049", "BharatBenz 1217C"),
}
COLOURS = ("White", "Silver", "Grey", "Black", "Red", "Blue", "Maroon", "Brown", "Green", "Yellow")
OFFICES = {
    "KL": (
        "Ernakulam RTO",
        "Thiruvananthapuram RTO",
        "Kozhikode RTO",
        "Thrissur RTO",
        "Kollam RTO",
        "Palakkad RTO",
        "Kannur RTO",
        "Malappuram RTO",
    ),
    "KA": ("Bengaluru Central RTO", "Mysuru RTO", "Mangaluru RTO"),
    "TN": ("Chennai Central RTO", "Coimbatore RTO", "Madurai RTO"),
    "MH": ("Mumbai Central RTO", "Pune RTO", "Nagpur RTO"),
    "DL": ("Delhi South RTO", "Delhi West RTO"),
    "AP": ("Vijayawada RTO", "Visakhapatnam RTO"),
    "TS": ("Hyderabad Central RTO",),
    "GJ": ("Ahmedabad RTO", "Surat RTO"),
    "HR": ("Gurugram RTO", "Faridabad RTO"),
    "UP": ("Lucknow RTO", "Noida RTO"),
    "RJ": ("Jaipur RTO", "Jodhpur RTO"),
    "WB": ("Kolkata RTO", "Howrah RTO"),
    "PY": ("Puducherry RTO",),
    "GA": ("Panaji RTO",),
    "PB": ("Ludhiana RTO", "Amritsar RTO"),
    "MP": ("Bhopal RTO", "Indore RTO"),
    "OD": ("Bhubaneswar RTO",),
    "BH": ("Bharat Series",),
}
EXTRA_NUMBERS = ("KL07CA1001", "KL11AZ2020", "KA03MN4455", "TN22BX7788", "MH12QR0909", "DL8CAF3344")


@dataclass(frozen=True)
class SeedOutcome:
    confirmed_numbers: int
    """Distinct confirmed numbers found in the processed videos."""
    created_from_videos: int
    created_extra: int
    skipped_existing: int
    created_near: int = 0
    """Near-miss records: one character from a confirmed number that has no record of its own."""


def confirmed_numbers(session: Session) -> dict[str, str]:
    """Distinct confirmed registration numbers in the latest runs, with the vehicle type seen."""
    rows = session.execute(
        select(RecognitionEvent.registration_number, VehicleTrack.vehicle_type)
        .join(VehicleTrack, VehicleTrack.id == RecognitionEvent.track_pk)
        .where(RecognitionEvent.job_id.in_(latest_completed_jobs()), RecognitionEvent.status == CONFIRMED)
        .order_by(RecognitionEvent.registration_number)
    ).all()
    numbers: dict[str, str] = {}
    for number, vehicle_type in rows:
        if number and number not in numbers:
            numbers[number] = vehicle_type
    return numbers


def make_entry(number: str, vehicle_type: str, rng: random.Random, today: date) -> DemoRegistryEntry:
    state = number[:2]
    offices = OFFICES.get(state, ("Regional Transport Office",))
    return DemoRegistryEntry(
        registration_number=number,
        owner_name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
        vehicle_description=rng.choice(VEHICLES.get(vehicle_type, VEHICLES["Car"])),
        vehicle_type=vehicle_type if vehicle_type in VEHICLES else "Car",
        colour=rng.choice(COLOURS),
        registered_at=rng.choice(offices),
        valid_until=today + timedelta(days=rng.randint(90, 5 * 365)),
        note=NOTE,
    )


def near_miss(number: str, rng: random.Random, taken: set[str]) -> str | None:
    """A valid plate one look-alike character away from `number` that no record or vehicle has yet."""
    positions = list(range(len(number)))
    rng.shuffle(positions)
    for position in positions:
        character = number[position]
        swap = LOOKALIKE_DIGIT.get(character) if character.isdigit() else LOOKALIKE_LETTER.get(character)
        if swap is None:
            continue
        candidate = number[:position] + swap + number[position + 1 :]
        if candidate not in taken and is_valid_plate(candidate):
            return candidate
    return None


def seed(
    session: Session,
    share: float = 0.5,
    extra: int = 4,
    seed_value: int = 2026,
    reset: bool = False,
    near: float = 0.25,
) -> SeedOutcome:
    """Create fictional records for about `share` of the confirmed numbers, plus `extra` unseen numbers, plus
    near-miss records (one character away) for about `near` of the confirmed numbers left without a record.

    Deterministic for a given seed and set of numbers, so running it again adds nothing new.
    """
    rng = random.Random(seed_value)
    today = date.today()
    if reset:
        for entry in session.scalars(select(DemoRegistryEntry)).all():
            session.delete(entry)
        session.flush()
    existing = set(session.scalars(select(DemoRegistryEntry.registration_number)).all())
    numbers = confirmed_numbers(session)
    chosen = [number for number in sorted(numbers) if rng.random() < share]
    created_from_videos = skipped = 0
    for number in chosen:
        if number in existing:
            skipped += 1
            continue
        session.add(make_entry(number, numbers[number], rng, today))
        existing.add(number)
        created_from_videos += 1
    created_extra = 0
    for number in EXTRA_NUMBERS[: max(0, extra)]:
        if number in existing or number in numbers:
            continue
        session.add(make_entry(number, rng.choice(("Car", "Motorcycle")), rng, today))
        existing.add(number)
        created_extra += 1
    # Near-miss records: drawn after the others so the records above come out the same as before.
    notes = session.scalars(select(DemoRegistryEntry.note)).all()
    already_near = {
        note.split("one character from ")[-1].rstrip(").") for note in notes if "one character from" in note
    }
    created_near = 0
    for number in sorted(numbers):
        if number in existing or number in already_near or rng.random() >= near:
            continue
        candidate = near_miss(number, rng, existing | set(numbers))
        if candidate is None:
            continue
        entry = make_entry(candidate, numbers[number], rng, today)
        entry.note = NEAR_NOTE.format(number=number)
        session.add(entry)
        existing.add(candidate)
        created_near += 1
    session.flush()
    return SeedOutcome(len(numbers), created_from_videos, created_extra, skipped, created_near)
