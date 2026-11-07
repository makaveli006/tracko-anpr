"""Count a label sheet against the system's answers (ARCHITECTURE.md, "HOW TO MEASURE REAL ACCURACY", step 4).

    uv run python tools/measure_accuracy.py labels/zoomed-in_system.csv labels/zoomed-in_truth.csv

A true number with `?` in it was only partly legible: it can show a reading to be wrong or
consistent, but it cannot prove one right, so such rows are "not checkable" and stay out of the
accuracy. The margin is the procedure's ±1/√n.

The export lists counted vehicles only, so a labelled track missing from it is one the system
merged into another. That is right when the label says it is a repeat too. When the label says
it is a vehicle of its own, a real vehicle has been lost from the count, and it is reported.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

from tracko_anpr.pipeline.validation import edit_distance


def margin(count: int) -> float | None:
    return 1 / math.sqrt(count) if count else None


def known(row: dict) -> bool:
    return bool(row["true_number"]) and "?" not in row["true_number"]


@dataclass
class Measurement:
    labelled: int = 0
    false_tracks: int = 0
    duplicates: int = 0
    vehicles: int = 0
    confirmed: int = 0
    correct: int = 0
    wrong: list[dict] = field(default_factory=list)
    not_checkable: list[dict] = field(default_factory=list)
    readable: int = 0
    unconfirmed: dict[str, int] = field(default_factory=dict)
    type_errors: list[dict] = field(default_factory=list)
    confirmed_on_duplicates: list[dict] = field(default_factory=list)
    merged_by_system: int = 0
    lost_vehicles: list[dict] = field(default_factory=list)
    """Labelled as a vehicle of its own, but merged away by the system."""

    @property
    def accuracy(self) -> float | None:
        checked = self.correct + len(self.wrong)
        return self.correct / checked if checked else None

    @property
    def recall(self) -> float | None:
        return self.correct / self.readable if self.readable else None


def measure(system: list[dict], truth: list[dict]) -> Measurement:
    """Join the two sheets on `track` and count, over real vehicles that are not repeats."""
    answers = {row["track"]: row for row in system}
    result = Measurement(labelled=len(truth))
    result.unconfirmed = {"right number": 0, "wrong number": 0, "no number": 0, "not checkable": 0}
    for label in truth:
        answer = answers.get(label["track"])
        if answer is None:
            result.merged_by_system += 1
            if label["is_vehicle"] != "yes":
                result.false_tracks += 1
            elif label["duplicate_of"]:
                result.duplicates += 1
            else:
                result.vehicles += 1
                result.lost_vehicles.append(label)
            continue
        row = {**label, "system_number": answer["registration_number"], "system_status": answer["status"]}
        if label["is_vehicle"] != "yes":
            result.false_tracks += 1
            continue
        if label["duplicate_of"]:
            result.duplicates += 1
            if answer["status"] == "confirmed":
                result.confirmed_on_duplicates.append(row)
            continue
        result.vehicles += 1
        if label["true_type"] != answer["vehicle_type"]:
            result.type_errors.append({**row, "system_type": answer["vehicle_type"]})
        legible = label["plate_legible"] == "yes" and known(label)
        result.readable += legible
        same = answer["registration_number"] == label["true_number"]
        if answer["status"] == "confirmed":
            result.confirmed += 1
            if not known(label):
                result.not_checkable.append(row)
            elif same:
                result.correct += 1
            else:
                errors = edit_distance(answer["registration_number"], label["true_number"])
                result.wrong.append({**row, "character_errors": errors})
        elif not answer["registration_number"]:
            result.unconfirmed["no number"] += 1
        elif not known(label):
            result.unconfirmed["not checkable"] += 1
        else:
            result.unconfirmed["right number" if same else "wrong number"] += 1
    return result


def percent(share: float | None, count: int) -> str:
    if share is None:
        return "not measurable"
    return f"{100 * share:.0f}% ±{100 * margin(count):.0f} points (n={count})"


def report(m: Measurement) -> str:
    checked = m.correct + len(m.wrong)
    lines = [
        f"Tracks labelled          {m.labelled}",
        f"False tracks             {m.false_tracks}",
        f"Repeats of a vehicle     {m.duplicates}",
        f"Real distinct vehicles   {m.vehicles}",
        f"Vehicles counted         {m.labelled - m.merged_by_system} ({m.merged_by_system} tracks merged, "
        f"{len(m.lost_vehicles)} of them real vehicles lost)",
        f"Confirmed among them     {m.confirmed} ({m.correct} correct, {len(m.wrong)} wrong, "
        f"{len(m.not_checkable)} not checkable)",
        f"Reading accuracy         {percent(m.accuracy, checked)}",
        f"Readable plates          {m.readable}",
        f"Reading recall           {percent(m.recall, m.readable)}",
        "Unconfirmed vehicles     " + ", ".join(f"{count} {name}" for name, count in m.unconfirmed.items()),
        f"Type errors              {len(m.type_errors)} of {m.vehicles}",
    ]
    for title, rows, columns in (
        ("Wrong confirmations", m.wrong, ("track", "system_number", "true_number", "character_errors")),
        ("Confirmed, not checkable", m.not_checkable, ("track", "system_number", "true_number")),
        ("Confirmed on a repeat track", m.confirmed_on_duplicates, ("track", "system_number", "true_number")),
        ("Type errors", m.type_errors, ("track", "system_type", "true_type")),
        ("Real vehicles lost to a merge", m.lost_vehicles, ("track", "true_type", "note")),
    ):
        if rows:
            lines += ["", title] + ["  " + "  ".join(str(row[column]) for column in columns) for row in rows]
    return "\n".join(lines)


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("system", type=Path, help="The exported CSV of the system's answers.")
    parser.add_argument("truth", type=Path, help="The label sheet.")
    args = parser.parse_args()
    print(report(measure(read(args.system), read(args.truth))))


if __name__ == "__main__":
    main()
