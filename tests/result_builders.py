"""Builders for pipeline results, shared by the database and worker tests.

They stand in for `run_pipeline`: a `PipelineResult` with a handful of tracks covering every
case the tables and the figures must handle (counted, too brief, camera car, repeat; confirmed,
unconfirmed, not detected), with file paths under a made-up project root.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from tracko_anpr.pipeline.direction import Direction
from tracko_anpr.pipeline.runner import PipelineResult, PlateSighting, VehicleRecord, summarize
from tracko_anpr.pipeline.validation import CONFIRMED, NOT_DETECTED, UNCONFIRMED, PlateDecision
from tracko_anpr.pipeline.video import VideoInfo

ROOT = Path("/project")
FPS = 30.0


def video_info(name: str = "clip_part01", duration_s: float = 120.0) -> VideoInfo:
    return VideoInfo(ROOT / "videos" / f"{name}.mp4", 1920, 1080, Fraction(30), int(duration_s * FPS), duration_s)


def sighting(track_id: int, frame: int, text: str, confidence: float) -> PlateSighting:
    crop = ROOT / "storage" / "plate_crops" / "clip_part01" / f"T{track_id}_f{frame:06d}.png"
    return PlateSighting(track_id, frame, (10.0, 20.0, 110.0, 50.0), 0.9, crop, text=text, confidence=confidence)


def vehicle(
    track_id: int,
    class_name: str,
    first_frame: int,
    last_frame: int,
    decision: PlateDecision | None = None,
    countable: bool = True,
    camera_car: bool = False,
    same_vehicle_as: int | None = None,
    sightings: list[PlateSighting] | None = None,
    direction: Direction | None = None,
) -> VehicleRecord:
    record = VehicleRecord(
        track_id=track_id,
        class_name=class_name,
        first_frame=first_frame,
        last_frame=last_frame,
        frames_seen=last_frame - first_frame + 1,
        best_confidence=0.9,
        countable=countable,
        camera_car=camera_car,
        decision=decision,
        same_vehicle_as=same_vehicle_as,
        sightings=sightings or [],
        direction=direction or Direction(),
        vehicle_crop=ROOT / "storage" / "vehicle_crops" / "clip_part01" / f"T{track_id}.jpg" if countable else None,
    )
    if decision is not None and decision.text and record.sightings:
        agreeing = [s for s in record.sightings if s.text == decision.text] or record.sightings
        record.plate_crop = agreeing[0].crop_file
    return record


def confirmed(text: str) -> PlateDecision:
    return PlateDecision(CONFIRMED, text, confidence=0.93, support=3, readings=4, share=0.8)


def a_result(info: VideoInfo | None = None) -> PipelineResult:
    """Six tracks: four count as vehicles (two confirmed, one unconfirmed, one not detected),
    one is too brief, one is the camera car; one confirmed vehicle appears again as a repeat."""
    info = info or video_info()
    vehicles = [
        vehicle(
            1,
            "Car",
            0,
            90,
            confirmed("KL07AB1234"),
            direction=Direction("towards", None),
            sightings=[
                sighting(1, 20, "KL07AB1Z34", 0.7),
                sighting(1, 30, "KL07AB1234", 0.95),
                sighting(1, 40, "KL07AB1234", 0.9),
            ],
        ),  # fmt: skip
        vehicle(
            2,
            "Motorcycle",
            300,
            400,
            PlateDecision(UNCONFIRMED, "KL39S3333", 0.7, 1, 2, 0.5, "one frame"),
            direction=Direction("away", None),
        ),  # fmt: skip
        vehicle(3, "Truck", 700, 800, PlateDecision(NOT_DETECTED, reason="no plate found")),
        vehicle(4, "Bus", 20, 25, countable=False),  # too brief
        vehicle(5, "Car", 0, 3500, countable=False, camera_car=True),
        vehicle(6, "Car", 1500, 1600, confirmed("KL07AB1234"), same_vehicle_as=1),
        vehicle(
            7,
            "Car",
            3300,
            3400,
            confirmed("KL10CD5678"),
            direction=Direction("towards", "left"),
            sightings=[sighting(7, 3350, "KL10CD5678", 0.91)],
        ),  # fmt: skip
    ]
    summary = summarize(vehicles)
    timings = {"detection_and_tracking_s": 100.0, "total_s": 200.0}
    out = ROOT / "storage" / "processed" / info.path.stem
    files = {
        "results": out / "results.json",
        "detections": out / "detections.csv",
        "plates": out / "plates.csv",
        "annotated_video": out / "annotated.mp4",
    }
    document = {
        "frames_processed": info.frame_count,
        "summary": summary,
        "timings": timings,
        "memory": {"gpu_pytorch_peak_mib": 1646, "ram_peak_mib": 2200},
        "settings": {"vehicle_image_size": 1536},
        "plates_examined": 4,
    }
    return PipelineResult(info, vehicles, summary, timings, files, document)
