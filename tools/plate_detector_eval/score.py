"""Score the plate-detector candidates from the sandbox's output. Runs in the main environment.

Two steps, with the plate reader run in between (it lives in the separate `ocr/` environment):

    uv run python tools/plate_detector_eval/score.py crops      # cut every plate each candidate found
    cd ocr
    uv run anpr-ocr read ../storage/plate_crops/phase4_eval \
        --json ../storage/plate_crops/phase4_eval/readings.json
    cd ..
    uv run python tools/plate_detector_eval/score.py report     # table, CSV and contact sheets

There is no hand-labelled ground truth, so candidates are judged by what matters downstream:
on how many vehicles they find a plate that the reader then turns into a confident,
plate-shaped registration number, and how often they agree with the other candidates.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from tracko_anpr.config import get_settings
from tracko_anpr.pipeline.cropping import crop_region

DETECTION_CONFIDENCE = 0.25
READING_CONFIDENCE = 0.85
PLATE_PAD_X, PLATE_PAD_Y = 0.05, 0.08
MIN_PLATE_WIDTH, MIN_PLATE_HEIGHT = 16, 8
PLATE_TEXT = re.compile(r"^(?:[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{1,4}|\d{2}BH\d{4}[A-Z]{1,2})$")
CONSENSUS_MIN_CANDIDATES = 3
SHEET_CROPS = 24


def load(settings):
    vehicles_dir = settings.vehicle_crops_dir / "phase4_eval"
    results_dir = settings.processed_dir / "phase4_eval"
    with (vehicles_dir / "index.csv").open(encoding="utf-8") as handle:
        index = {row["file"]: row for row in csv.DictReader(handle)}
    candidates = {}
    for path in sorted(results_dir.glob("detections_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        candidates[record["candidate"]] = record
    return vehicles_dir, results_dir, index, candidates


def top_box(record: dict, file: str):
    boxes = record.get("detections", {}).get(file) or []
    return boxes[0] if boxes and boxes[0][4] >= DETECTION_CONFIDENCE else None


def plate_name(candidate: str, file: str) -> str:
    return f"{candidate}__{Path(file).stem}.png"


def make_crops() -> None:
    settings = get_settings()
    vehicles_dir, _, index, candidates = load(settings)
    out = settings.plate_crops_dir / "phase4_eval"
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.png"):
        stale.unlink()

    total = 0
    for file in index:
        image = cv2.imread(str(vehicles_dir / file))
        for name, record in candidates.items():
            box = top_box(record, file)
            if box is None:
                continue
            crop = crop_region(image, tuple(box[:4]), PLATE_PAD_X, PLATE_PAD_Y)
            if crop is None or crop.width < MIN_PLATE_WIDTH or crop.height < MIN_PLATE_HEIGHT:
                continue
            cv2.imwrite(str(out / plate_name(name, file)), crop.image)
            total += 1
    print(f"{total} plate crops from {len(candidates)} candidates -> {out}")


def report() -> None:
    settings = get_settings()
    vehicles_dir, results_dir, index, candidates = load(settings)
    plates_dir = settings.plate_crops_dir / "phase4_eval"
    readings = {r["image"]: r for r in json.loads((plates_dir / "readings.json").read_text(encoding="utf-8"))}
    vehicle_of = {file: (row["clip"], row["track_id"]) for file, row in index.items()}
    all_vehicles = set(vehicle_of.values())

    def reading(name: str, file: str):
        return readings.get(plate_name(name, file))

    def confident_text(name: str, file: str) -> str | None:
        found = reading(name, file)
        if found and found["confidence"] >= READING_CONFIDENCE and PLATE_TEXT.match(found["text"] or ""):
            return found["text"]
        return None

    # What each candidate read for each vehicle (a vehicle has up to two crops).
    per_vehicle: dict[str, dict[tuple, list[str]]] = {name: defaultdict(list) for name in candidates}
    for name in candidates:
        for file in index:
            text = confident_text(name, file)
            if text:
                per_vehicle[name][vehicle_of[file]].append(text)

    # A vehicle's consensus number: the text most candidates read for it, if enough of them agree.
    consensus = {}
    for vehicle in all_vehicles:
        votes = Counter()
        for name in candidates:
            for text in set(per_vehicle[name].get(vehicle, [])):
                votes[text] += 1
        if votes:
            text, count = votes.most_common(1)[0]
            if count >= CONSENSUS_MIN_CANDIDATES:
                consensus[vehicle] = text

    rows = []
    for name, record in candidates.items():
        if "error" in record:
            rows.append({"candidate": name, "error": record["error"]})
            continue
        boxed = [file for file in index if top_box(record, file) is not None]
        widths = [top_box(record, file)[2] - top_box(record, file)[0] for file in boxed]
        read = [reading(name, file) for file in boxed]
        weak = sum(1 for r in read if r is None or r["unreadable"] or r["confidence"] < 0.5)
        vehicles_boxed = {vehicle_of[file] for file in boxed}
        vehicles_read = set(per_vehicle[name])
        two_frames = sum(1 for texts in per_vehicle[name].values() if Counter(texts).most_common(1)[0][1] >= 2)
        matched = sum(1 for vehicle, text in consensus.items() if text in per_vehicle[name].get(vehicle, []))
        differs = sum(
            1
            for vehicle, text in consensus.items()
            if per_vehicle[name].get(vehicle) and text not in per_vehicle[name][vehicle]
        )
        rows.append(
            {
                "candidate": name,
                "file": record["file"],
                "input_size": record["image_size"],
                "classes": "/".join(record["class_names"][k] for k in sorted(record["class_names"], key=int))
                if isinstance(next(iter(record["class_names"])), str)
                else "/".join(record["class_names"].values()),
                "crops_with_plate": len(boxed),
                "crops_with_plate_pct": round(100 * len(boxed) / len(index), 1),
                "vehicles_with_plate": len(vehicles_boxed),
                "vehicles_read": len(vehicles_read),
                "vehicles_read_pct": round(100 * len(vehicles_read) / len(all_vehicles), 1),
                "vehicles_two_frames_agree": two_frames,
                "consensus_matched": matched,
                "consensus_matched_pct": round(100 * matched / len(consensus), 1) if consensus else 0.0,
                "consensus_differs": differs,
                "weak_boxes_pct": round(100 * weak / len(boxed), 1) if boxed else 0.0,
                "median_plate_width": round(statistics.median(widths)) if widths else 0,
                "ms_per_crop_cpu": record.get("ms_per_crop_cpu", 0.0),
            }
        )

    ranked = sorted((r for r in rows if "error" not in r), key=lambda r: (-r["vehicles_read"], -r["consensus_matched"]))
    failed = [r for r in rows if "error" in r]

    with (results_dir / "comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ranked[0]))
        writer.writeheader()
        writer.writerows(ranked)

    print(f"vehicle crops: {len(index)} | vehicles: {len(all_vehicles)}")
    print(f"vehicles with a consensus number: {len(consensus)}")
    columns = [("candidate", "<20"), ("plate found", ">12"), ("vehicles", ">10"), ("READ", ">7"), ("%", ">6")]
    columns += [("2 frames", ">9"), ("consensus", ">10"), ("differs", ">8"), ("weak %", ">8"), ("width", ">7")]
    columns += [("ms", ">7")]
    print("".join(format(title, spec) for title, spec in columns))
    for r in ranked:
        print(
            f"{r['candidate']:<20}{r['crops_with_plate']:>8} {r['crops_with_plate_pct']:>3.0f}%"
            f"{r['vehicles_with_plate']:>9}"
            f"{r['vehicles_read']:>7}{r['vehicles_read_pct']:>6.1f}{r['vehicles_two_frames_agree']:>9}"
            f"{r['consensus_matched']:>6}/{len(consensus):<3}{r['consensus_differs']:>8}{r['weak_boxes_pct']:>8.1f}"
            f"{r['median_plate_width']:>7}{r['ms_per_crop_cpu']:>7.0f}"
        )
    for r in failed:
        print(f"{r['candidate']:<20} FAILED: {r['error']}")

    # Per-clip view of the key figure, to see whether a candidate is only good on some footage.
    clips = sorted({row["clip"] for row in index.values()})
    print("\nvehicles read per clip (of vehicles in the clip):")
    print(f"{'candidate':<20}" + "".join(f"{clip[:13]:>15}" for clip in clips))
    totals = Counter(clip for clip, _ in all_vehicles)
    for r in ranked[:8]:
        counts = Counter(clip for clip, _ in per_vehicle[r["candidate"]])
        print(f"{r['candidate']:<20}" + "".join(f"{counts[clip]:>9}/{totals[clip]:<5}" for clip in clips))

    # Contact sheets: the same vehicle crops for every candidate, with its box and what was read.
    by_clip = defaultdict(list)
    for file, row in index.items():
        by_clip[row["clip"]].append(file)
    sample = []
    for clip in clips:
        files = sorted(by_clip[clip], key=lambda f: -int(index[f]["width"]) * int(index[f]["height"]))
        step = max(1, len(files) // (SHEET_CROPS // len(clips)))
        sample += files[::step][: SHEET_CROPS // len(clips)]

    def tile(name: str, file: str, cell=(330, 250)) -> np.ndarray:
        image = cv2.imread(str(vehicles_dir / file))
        box = top_box(candidates[name], file)
        if box is not None:
            x1, y1, x2, y2 = (round(v) for v in box[:4])
            cv2.rectangle(image, (x1, y1), (x2, y2), (21, 204, 250), max(2, image.shape[0] // 150))
        scale = min(200 / image.shape[0], (cell[0] - 10) / image.shape[1])
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        canvas = np.full((cell[1], cell[0], 3), 30, np.uint8)
        canvas[5 : 5 + image.shape[0], 5 : 5 + image.shape[1]] = image
        found = reading(name, file) if box is not None else None
        if box is None:
            text, colour = "no plate found", (150, 150, 150)
        elif found is None or found["unreadable"]:
            text, colour = "plate found, unreadable", (150, 150, 150)
        else:
            good = found["confidence"] >= READING_CONFIDENCE and PLATE_TEXT.match(found["text"] or "")
            text, colour = f"{found['text']}  {found['confidence']:.2f}", (60, 200, 60) if good else (40, 160, 240)
        cv2.putText(canvas, text, (6, 228), cv2.FONT_HERSHEY_SIMPLEX, 0.58, colour, 2, cv2.LINE_AA)
        cv2.putText(
            canvas, index[file]["clip"][:22], (6, 245), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (170, 170, 170), 1, cv2.LINE_AA
        )
        return canvas

    for r in ranked[:6]:
        tiles = [tile(r["candidate"], file) for file in sample]
        columns = 6
        while len(tiles) % columns:
            tiles.append(np.full_like(tiles[0], 30))
        grid = np.vstack([np.hstack(tiles[i : i + columns]) for i in range(0, len(tiles), columns)])
        title = np.full((44, grid.shape[1], 3), 20, np.uint8)
        cv2.putText(
            title,
            f"{r['candidate']}   ({r['file']})   vehicles read: {r['vehicles_read']} of {len(all_vehicles)}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA,
        )  # fmt: skip
        cv2.imwrite(
            str(results_dir / f"sheet_{r['candidate']}.jpg"), np.vstack([title, grid]), [cv2.IMWRITE_JPEG_QUALITY, 92]
        )
    print(f"\ncontact sheets for the top {min(6, len(ranked))} candidates and comparison.csv -> {results_dir}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "crops":
        make_crops()
    elif command == "report":
        report()
    else:
        print(__doc__)
        raise SystemExit(2)
