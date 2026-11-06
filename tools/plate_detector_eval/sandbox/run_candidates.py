"""Run every plate-detector candidate over the evaluation crops. Runs INSIDE the sandbox container only.

Inputs (read-only mounts):  /weights  the candidate files,  /crops  vehicle crops plus index.csv
Output (the only writable mount):  /out/detections_<candidate>.json

For each vehicle crop it records the plate boxes the candidate found, in the crop's own pixels.
Nothing is judged here; scoring happens outside the sandbox, on these plain JSON files.
"""

from __future__ import annotations

import csv
import json
import time
import traceback
from pathlib import Path

import cv2

WEIGHTS, CROPS, OUT = Path("/weights"), Path("/crops"), Path("/out")
CONFIDENCE = 0.10  # kept low on purpose; the scoring step applies its own thresholds
BATCH = 16

# name, file under /weights, input size. ONNX files have a fixed input size.
CANDIDATES = [
    ("dushyant-26n-onnx", "DushyantRajpurohit__indian-anpr/detector.onnx", 416),
    ("purvraj-26m", "purvrajsinhjadeja31105-dotcom__smart-helmet-detection/plate_crop_best.pt", 640),
    ("nishant-26n", "nishantjaat9712__Ai-Parking-Slot-Detection/best.pt", 640),
    ("dinesh-26s", "dinesh2068__Mainproject-phase-1/indian_plate_yolo26s.pt", 640),
    ("tejas-26s-onnx", "Tejascodz__drishti/plate_yolo26s_in_960.onnx", 960),
    ("sentry-26s", "ayannotfound__Sentry/best.pt", 640),
    ("tejaswi-26n", "tejaswi67__Vehicle-License-Plate-Detection/best_license_plate_model.pt", 640),
    ("hempixel-26s", "hem-pixel__number_plate_detection/best.pt", 640),
    ("harp-26n", "Harp404__DRISHTI/plate.pt", 640),
    ("dexit-26s", "dexitshallbe__NumberPlateDetection/my_model.pt", 640),
    ("vivekvar-11m", "other-models/vivekvar__helmet-v5/plate_yolo_ft.pt", 640),
    ("subash-v8n", "other-models/subash1652007__indian-plate-ocr/yolo_best.pt", 640),
    ("gursharn-v8n", "other-models/gursharn01__indian-license-plate-detector/no_plate_model.pt", 640),
    ("rajcreo-26s-4class", "other-models/rajcreo__traffic-violation-models/helmet_detector.pt", 640),
]
PLATE_WORDS = ("plate", "licen", "lp", "numplate", "number")


def plate_class_ids(names: dict[int, str]) -> list[int]:
    """The class ids that mean "number plate". Single-class models are plate detectors by definition."""
    if len(names) == 1:
        return list(names)
    return [
        index for index, name in names.items() if any(word in name.lower().replace("_", "") for word in PLATE_WORDS)
    ]


def run(name: str, relative: str, image_size: int, crops: list[dict]) -> dict:
    from ultralytics import YOLO

    started = time.perf_counter()
    model = YOLO(str(WEIGHTS / relative), task="detect")
    names = dict(model.names)
    wanted = plate_class_ids(names)
    record = {
        "candidate": name,
        "file": relative,
        "image_size": image_size,
        "class_names": names,
        "plate_class_ids": wanted,
        "detections": {},
    }
    if not wanted:
        record["error"] = "no class that looks like a number plate"
        return record

    load_seconds = time.perf_counter() - started
    predict_seconds = 0.0
    for start in range(0, len(crops), BATCH):
        batch = crops[start : start + BATCH]
        images = [cv2.imread(str(CROPS / row["file"])) for row in batch]
        began = time.perf_counter()
        results = model.predict(
            images, imgsz=image_size, conf=CONFIDENCE, classes=wanted, device="cpu", max_det=10, verbose=False
        )
        predict_seconds += time.perf_counter() - began
        for row, result in zip(batch, results, strict=True):
            boxes = result.boxes
            found = []
            if boxes is not None and len(boxes):
                order = boxes.conf.argsort(descending=True)[:5]
                for index in order.tolist():
                    x1, y1, x2, y2 = (round(float(v), 1) for v in boxes.xyxy[index].tolist())
                    found.append([x1, y1, x2, y2, round(float(boxes.conf[index]), 4)])
            record["detections"][row["file"]] = found
    record["load_seconds"] = round(load_seconds, 2)
    record["ms_per_crop_cpu"] = round(1000 * predict_seconds / max(1, len(crops)), 1)
    return record


def main() -> None:
    with (CROPS / "index.csv").open(encoding="utf-8") as handle:
        crops = list(csv.DictReader(handle))
    print(f"{len(crops)} vehicle crops, {len(CANDIDATES)} candidates", flush=True)

    for name, relative, image_size in CANDIDATES:
        try:
            record = run(name, relative, image_size, crops)
        except Exception as error:  # one bad file must not stop the others
            record = {"candidate": name, "file": relative, "error": f"{type(error).__name__}: {error}"}
            traceback.print_exc()
        (OUT / f"detections_{name}.json").write_text(json.dumps(record), encoding="utf-8")
        if "error" in record:
            print(f"  {name}: FAILED - {record['error']}", flush=True)
        else:
            found = sum(1 for boxes in record["detections"].values() if boxes)
            print(
                f"  {name}: classes {record['class_names']}, boxes on {found}/{len(crops)} crops, "
                f"{record['ms_per_crop_cpu']} ms per crop on CPU",
                flush=True,
            )


if __name__ == "__main__":
    main()
