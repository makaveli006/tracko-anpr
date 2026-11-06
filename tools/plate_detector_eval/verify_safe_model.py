"""Check that the safely re-saved plate detector, loaded in the main environment on the GPU,
finds the same plates the original file found inside the sandbox.

    uv run python tools/plate_detector_eval/verify_safe_model.py sentry-26s

Compares, crop by crop, with storage/processed/phase4_eval/detections_<name>.json.
The sandbox ran on the CPU at full precision and this runs on the GPU at half precision,
so tiny differences in box position and confidence are expected; a different answer about
whether a plate is there is counted separately.
"""

from __future__ import annotations

import csv
import json
import sys
import time

import cv2

from tracko_anpr.config import get_settings
from tracko_anpr.pipeline.plates import PlateDetector

THRESHOLD = 0.25


def overlap(a, b) -> float:
    """Intersection over union of two boxes."""
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    shared = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    total = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - shared
    return shared / total if total > 0 else 0.0


def main(name: str) -> int:
    settings = get_settings()
    crops_dir = settings.vehicle_crops_dir / "phase4_eval"
    sandbox = json.loads((settings.processed_dir / "phase4_eval" / f"detections_{name}.json").read_text("utf-8"))
    with (crops_dir / "index.csv").open(encoding="utf-8") as handle:
        files = [row["file"] for row in csv.DictReader(handle)]

    detector = PlateDetector(settings.models_dir / "plate" / f"{name}.safetensors", confidence=THRESHOLD)
    print(f"loaded {name} from plain files; running on {'GPU' if detector.on_gpu else 'CPU'} at {detector.precision}")
    images = [cv2.imread(str(crops_dir / file)) for file in files]
    detector.detect(images[:8])  # warm-up
    started = time.perf_counter()
    found = detector.detect(images)
    seconds = time.perf_counter() - started

    both = same_place = only_sandbox = only_here = neither = 0
    confidence_gap = []
    borderline = 0
    for file, plates in zip(files, found, strict=True):
        before = [box for box in sandbox["detections"].get(file, []) if box[4] >= THRESHOLD]
        if before and plates:
            both += 1
            if overlap(before[0][:4], plates[0].box) >= 0.9:
                same_place += 1
            confidence_gap.append(abs(before[0][4] - plates[0].confidence))
        elif before:
            only_sandbox += 1
            borderline += before[0][4] < THRESHOLD + 0.03
        elif plates:
            only_here += 1
            borderline += plates[0].confidence < THRESHOLD + 0.03
        else:
            neither += 1

    print(f"crops: {len(files)}")
    print(f"  plate in both runs:        {both}  (same place, overlap 0.9 or more: {same_place})")
    print(f"  no plate in either run:    {neither}")
    print(f"  plate only in the sandbox: {only_sandbox}")
    print(f"  plate only here:           {only_here}")
    print(f"  of the disagreements, confidence within 0.03 of the threshold: {borderline}")
    if confidence_gap:
        print(f"  largest confidence difference where both found a plate: {max(confidence_gap):.3f}")
    print(f"speed on this machine: {1000 * seconds / len(files):.1f} ms per vehicle crop")
    agreement = (both + neither) / len(files)
    print(f"agreement on whether a plate is present: {100 * agreement:.1f}%")
    return 0 if agreement >= 0.98 and same_place >= 0.98 * both else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "sentry-26s"))
