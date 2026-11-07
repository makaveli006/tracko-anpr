"""Run the whole pipeline over one video.

The stages run one after another, each over the whole video, matching the timeline the
dashboard shows:

    1. video_uploaded
    2. vehicle_detection   } one pass: YOLO26m finds vehicles in every frame and
    3. vehicle_tracking    } TrackTrack follows them from frame to frame
    4. plate_detection     the plate detector looks at each vehicle in the frames where it is largest
    5. ocr                 the reader reads every plate that was found
    6. validation          each vehicle's readings are combined into one decision
    7. result_generation   the annotated video and the result files are written

Running the stages in sequence, not frame by frame, is what lets stage 4 choose a vehicle's
best frames with the whole track in hand, and lets stage 7 show only validated numbers.
"""

from __future__ import annotations

import csv
import json
import shutil
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2

from tracko_anpr.config import Settings
from tracko_anpr.pipeline.annotate import PlateLabel, render_annotated_video
from tracko_anpr.pipeline.cropping import Box, best_frames, box_area, crop_region
from tracko_anpr.pipeline.ocr_client import OcrClient
from tracko_anpr.pipeline.plates import PlateDetector, cut_plate
from tracko_anpr.pipeline.results import frame_time, write_detections_csv
from tracko_anpr.pipeline.rules import TrackRules, box_height, is_camera_car, is_countable
from tracko_anpr.pipeline.tracking import VEHICLE_CLASSES, TrackingRun, VehicleTracker, format_track_id, track_video
from tracko_anpr.pipeline.validation import (
    CONFIRMED,
    NOT_DETECTED,
    UNCONFIRMED,
    Observation,
    PlateDecision,
    ValidationRules,
    correct,
    decide,
    normalize,
)
from tracko_anpr.pipeline.video import VideoError, VideoInfo, probe_video, read_selected_frames


def memory_peaks() -> dict[str, int]:
    """Most memory this process has held so far: PyTorch's GPU memory and the process's RAM, in MiB.

    Read at the end of a run so the figure covers every model that was loaded, not only the
    first. The GPU figure is 0 without CUDA; the RAM figure is 0 where the platform cannot say.
    """
    gpu_mib = 0.0
    ram_mib = 0.0
    try:
        import torch

        if torch.cuda.is_available():
            gpu_mib = torch.cuda.max_memory_reserved() / 2**20
    except ImportError:
        pass
    try:
        import resource

        ram_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux reports kilobytes
    except ImportError:
        pass
    return {"gpu_pytorch_peak_mib": round(gpu_mib), "ram_peak_mib": round(ram_mib)}


STAGES = (
    "video_uploaded",
    "vehicle_detection",
    "vehicle_tracking",
    "plate_detection",
    "ocr",
    "validation",
    "result_generation",
)

StageProgress = Callable[[str, int, int], None]
"""Called with (stage name, units done, units expected)."""

NOT_COUNTED = "not_counted"
"""Status of a track that is not a countable vehicle; it gets no plate decision."""


@dataclass(frozen=True)
class PipelineOptions:
    plate_frames_per_track: int = 6
    """How many frames of each vehicle are examined for its plate."""
    plate_frame_gap_seconds: float = 0.15
    """Examined frames of one vehicle are at least this far apart, so they are not near-copies."""
    vehicle_padding: float = 0.04
    """Margin kept around a vehicle box when it is cut out, as a fraction of the box."""
    track_rules: TrackRules = field(default_factory=TrackRules)
    validation: ValidationRules = field(default_factory=ValidationRules)
    render_video: bool = True
    max_seconds: float | None = None
    """Only process the start of the video (for quick checks)."""


@dataclass
class PlateSighting:
    """One plate found on one vehicle in one frame, and what the reader made of it."""

    track_id: int
    frame: int
    box: Box
    """Where the plate is, in original-frame pixels."""
    detector_confidence: float
    crop_file: Path
    text: str = ""
    confidence: float = 0.0
    unreadable: bool = False
    ctc_text: str = ""
    found_in: int | None = None
    """Track whose cut-out the plate was found in. It differs from `track_id` when the plate
    turned out to belong to a smaller vehicle overlapping that one (see `plate_owner`)."""


@dataclass
class VehicleRecord:
    """Everything the pipeline concluded about one track."""

    track_id: int
    class_name: str
    first_frame: int
    last_frame: int
    frames_seen: int
    best_confidence: float
    countable: bool
    camera_car: bool
    decision: PlateDecision | None = None
    vehicle_crop: Path | None = None
    plate_crop: Path | None = None
    sightings: list[PlateSighting] = field(default_factory=list)
    same_vehicle_as: int | None = None
    """Track id of an earlier track that turned out to be this same vehicle (same confirmed number)."""

    @property
    def status(self) -> str:
        return self.decision.status if self.decision is not None else NOT_COUNTED

    @property
    def counts_as_vehicle(self) -> bool:
        """True when this track adds one to Total Vehicles."""
        return self.countable and self.same_vehicle_as is None


@dataclass
class PipelineResult:
    info: VideoInfo
    vehicles: list[VehicleRecord]
    summary: dict
    timings: dict
    files: dict[str, Path]
    document: dict = field(default_factory=dict)
    """Everything written to results.json: video, summary, timings, speed, memory, settings, vehicles."""


def plate_owner(plate: Box, found_in: int, vehicle_boxes: dict[int, Box]) -> int:
    """Which vehicle a plate belongs to, given every countable vehicle's box in that frame.

    Vehicle boxes overlap in traffic: the box of a van seen from the side also takes in the back
    of the car ahead of it, number plate included. So a plate found inside vehicle `found_in`'s
    cut-out goes to the smallest vehicle box that contains the plate's centre. A vehicle in
    front of another has the smaller box, and it is the one whose plate can be seen.
    """
    centre_x, centre_y = (plate[0] + plate[2]) / 2, (plate[1] + plate[3]) / 2
    candidates = [
        (box_area(box), track_id)
        for track_id, box in vehicle_boxes.items()
        if track_id == found_in or (box[0] <= centre_x <= box[2] and box[1] <= centre_y <= box[3])
    ]
    return min(candidates)[1] if candidates else found_in


def settle_shared_numbers(vehicles: list[VehicleRecord]) -> None:
    """Let a number stay confirmed on only one of the vehicles that are in view at the same time.

    One registration number cannot be on two vehicles at once. When two tracks that overlap in
    time both arrive at the same confirmed number, the one with more agreeing frames keeps it
    and the other is marked unconfirmed, with the reason recorded.
    """
    by_number: dict[str, list[VehicleRecord]] = defaultdict(list)
    for vehicle in vehicles:
        if vehicle.countable and vehicle.status == CONFIRMED:
            by_number[vehicle.decision.text].append(vehicle)
    for group in by_number.values():
        kept: list[VehicleRecord] = []
        strongest_first = sorted(group, key=lambda v: (-v.decision.support, -v.decision.confidence, v.track_id))
        for vehicle in strongest_first:
            rival = next(
                (k for k in kept if vehicle.first_frame <= k.last_frame and k.first_frame <= vehicle.last_frame),
                None,
            )
            if rival is None:
                kept.append(vehicle)
            else:
                reason = f"same number as {format_track_id(rival.track_id)}, which was in view at the same time"
                vehicle.decision = replace(vehicle.decision, status=UNCONFIRMED, reason=reason)


def mark_repeat_tracks(vehicles: list[VehicleRecord]) -> None:
    """Find tracks that are the same vehicle seen again, and point them at the first one.

    The tracker gives a vehicle a new id when it loses it for a while (hidden behind a bus,
    out of frame and back). Two tracks with the same confirmed registration number are the
    same vehicle, so the later one must not be counted again. Tracks that overlap in time are
    left alone: one vehicle cannot be in two places at once, so that is a misreading, not a repeat.
    """
    first_with_number: dict[str, VehicleRecord] = {}
    last_frame_of: dict[str, int] = {}
    confirmed = [vehicle for vehicle in vehicles if vehicle.countable and vehicle.status == CONFIRMED]
    for vehicle in sorted(confirmed, key=lambda item: (item.first_frame, item.track_id)):
        number = vehicle.decision.text
        if number not in first_with_number:
            first_with_number[number] = vehicle
            last_frame_of[number] = vehicle.last_frame
        elif vehicle.first_frame > last_frame_of[number]:
            vehicle.same_vehicle_as = first_with_number[number].track_id
            last_frame_of[number] = max(last_frame_of[number], vehicle.last_frame)


def summarize(vehicles: list[VehicleRecord]) -> dict:
    """The headline figures. Only countable vehicles are counted; the rest are reported beside them."""
    counted = [vehicle for vehicle in vehicles if vehicle.counts_as_vehicle]
    statuses = Counter(vehicle.status for vehicle in counted)
    by_class = dict.fromkeys(VEHICLE_CLASSES.values(), 0)
    for vehicle in counted:
        by_class[vehicle.class_name] += 1
    confirmed = statuses[CONFIRMED]
    return {
        "unique_tracks": len(vehicles),
        "total_vehicles": len(counted),
        "camera_car_tracks": sum(1 for vehicle in vehicles if vehicle.camera_car),
        "tracks_too_brief_or_small": sum(1 for vehicle in vehicles if not vehicle.countable and not vehicle.camera_car),
        "repeat_tracks": sum(1 for vehicle in vehicles if vehicle.same_vehicle_as is not None),
        "by_class": by_class,
        "confirmed": confirmed,
        "unconfirmed": statuses[UNCONFIRMED],
        "not_detected": statuses[NOT_DETECTED],
        # Share of countable vehicles with a confirmed number. This is coverage, not accuracy.
        "recognition_coverage": round(confirmed / len(counted), 4) if counted else None,
    }


def best_plate_sighting(sightings: list[PlateSighting], decision: PlateDecision) -> PlateSighting | None:
    """The sighting whose crop best represents the vehicle's plate: one that agrees with the decision if possible."""
    if not sightings:
        return None

    def agrees(sighting: PlateSighting) -> bool:
        corrected = correct(sighting.text)
        return bool(decision.text) and (corrected[0] if corrected else normalize(sighting.text)) == decision.text

    return max(sightings, key=lambda sighting: (agrees(sighting), sighting.confidence, sighting.detector_confidence))


def _fresh_folder(path: Path) -> Path:
    """An empty folder at `path`: results of an earlier run of the same video are replaced, not mixed in."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def run_pipeline(
    video: str | Path,
    settings: Settings,
    options: PipelineOptions | None = None,
    progress: StageProgress | None = None,
    name: str | None = None,
) -> PipelineResult:
    """Process one MP4 from start to finish and write its results under `storage/`."""
    options = options or PipelineOptions()
    report = progress or (lambda stage, done, total: None)
    timings: dict[str, float] = {}
    started = time.perf_counter()

    info = probe_video(video)
    name = name or info.path.stem
    out_dir = _fresh_folder(settings.processed_dir / name)
    plates_dir = _fresh_folder(settings.plate_crops_dir / name)
    vehicles_dir = _fresh_folder(settings.vehicle_crops_dir / name)
    fps = info.fps_float
    max_frames = None if options.max_seconds is None else max(1, round(options.max_seconds * fps))
    report("video_uploaded", 1, 1)

    # --- stages 2 and 3: vehicle detection and tracking, one pass over the video ---------------
    stage_started = time.perf_counter()

    def tracking_progress(done: int, total: int) -> None:
        report("vehicle_detection", done, total)
        report("vehicle_tracking", done, total)

    with VehicleTracker(
        settings.vehicle_weights,
        fps,
        settings.vehicle_image_size,
        settings.vehicle_confidence,
        settings.tracker_lost_seconds,
    ) as tracker:
        run: TrackingRun = track_video(info, tracker, max_frames, tracking_progress)
        tracker_details = {
            "vehicle_weights": settings.vehicle_weights.name,
            "vehicle_image_size": tracker.image_size,
            "vehicle_confidence": tracker.confidence,
            "precision": tracker.precision,
            "tracker": "tracktrack",
            "track_buffer_frames": tracker.track_buffer,
        }
    if run.frame_count == 0:
        raise VideoError(f"No frames could be read from {info.path.name}.")
    timings["detection_and_tracking_s"] = time.perf_counter() - stage_started

    history: dict[int, list[tuple[int, Box]]] = defaultdict(list)
    for frame_index, tracked in enumerate(run.frames):
        for vehicle in tracked:
            history[vehicle.track_id].append((frame_index, vehicle.box))

    vehicles: dict[int, VehicleRecord] = {}
    for track_id, summary in run.registry.tracks.items():
        observations = history[track_id]

        def others_in_frame(frame_index: int, own: int = track_id) -> list[Box]:
            return [vehicle.box for vehicle in run.frames[frame_index] if vehicle.track_id != own]

        camera_car = is_camera_car(
            observations, info.width, info.height, fps, options.track_rules, others_in_frame=others_in_frame
        )
        vehicles[track_id] = VehicleRecord(
            track_id=track_id,
            class_name=summary.class_name,
            first_frame=summary.first_frame,
            last_frame=summary.last_frame,
            frames_seen=summary.frames_seen,
            best_confidence=summary.best_confidence,
            countable=not camera_car and is_countable(observations, info.height, fps, options.track_rules),
            camera_car=camera_car,
        )
    countable = [vehicle for vehicle in vehicles.values() if vehicle.countable]

    # --- stage 4: plate detection on each vehicle's best frames -------------------------------
    stage_started = time.perf_counter()
    gap = max(1, round(fps * options.plate_frame_gap_seconds))
    wanted: dict[int, list[tuple[int, Box, bool]]] = defaultdict(list)
    for vehicle in countable:
        boxes = dict(history[vehicle.track_id])
        chosen = best_frames(history[vehicle.track_id], info.width, info.height, options.plate_frames_per_track, gap)
        for position, frame_index in enumerate(chosen):
            wanted[frame_index].append((vehicle.track_id, boxes[frame_index], position == 0))

    detector = PlateDetector(settings.plate_weights, settings.plate_image_size, settings.plate_confidence)
    countable_ids = {vehicle.track_id for vehicle in countable}
    found_plates: dict[tuple[int, int], PlateSighting] = {}  # one plate per vehicle per frame
    pending: list[tuple[int, int, object, bool]] = []

    def countable_boxes(frame_index: int) -> dict[int, Box]:
        return {v.track_id: v.box for v in run.frames[frame_index] if v.track_id in countable_ids}

    def examine(batch: list[tuple[int, int, object, bool]]) -> None:
        found = detector.detect([crop.image for _, _, crop, _ in batch])
        for (track_id, frame_index, crop, is_best), plates in zip(batch, found, strict=True):
            if is_best:
                path = vehicles_dir / f"{format_track_id(track_id)}.jpg"
                cv2.imwrite(str(path), crop.image, [cv2.IMWRITE_JPEG_QUALITY, 92])
                vehicles[track_id].vehicle_crop = path
            boxes = countable_boxes(frame_index) if plates else {}
            for plate in plates:
                # A vehicle's cut-out can also show the plate of a smaller vehicle overlapping it.
                plate_box = crop.to_frame(plate.box)
                owner = plate_owner(plate_box, track_id, boxes)
                earlier = found_plates.get((owner, frame_index))
                if earlier is not None and (earlier.found_in == owner, earlier.detector_confidence) >= (
                    track_id == owner,
                    plate.confidence,
                ):
                    continue  # the owner's own cut-out, or a surer detection, already gave this frame's plate
                plate_crop = cut_plate(crop.image, plate)
                if plate_crop is None:
                    continue
                path = plates_dir / f"{format_track_id(owner)}_f{frame_index:06d}.png"
                cv2.imwrite(str(path), plate_crop.image)
                found_plates[(owner, frame_index)] = PlateSighting(
                    owner, frame_index, plate_box, plate.confidence, path, found_in=track_id
                )

    for frames_done, (frame_index, frame) in enumerate(read_selected_frames(info.path, set(wanted)), start=1):
        for track_id, box, is_best in wanted[frame_index]:
            crop = crop_region(frame, box, options.vehicle_padding, options.vehicle_padding)
            if crop is not None:
                pending.append((track_id, frame_index, crop, is_best))
        if len(pending) >= 32:
            examine(pending)
            pending = []
        if frames_done < len(wanted):  # the last frame is reported below, once its plates are examined
            report("plate_detection", frames_done, len(wanted))
    if pending:
        examine(pending)
    sightings = sorted(found_plates.values(), key=lambda sighting: (sighting.track_id, sighting.frame))
    report("plate_detection", len(wanted), len(wanted))
    timings["plate_detection_s"] = time.perf_counter() - stage_started

    # --- stage 5: read every plate that was found ---------------------------------------------
    stage_started = time.perf_counter()
    report("ocr", 0, len(sightings))
    if sightings:
        with OcrClient.for_project(
            settings.ocr_project,
            start_timeout=settings.ocr_start_timeout_seconds,
            request_timeout=settings.ocr_request_timeout_seconds,
        ) as reader:
            for start in range(0, len(sightings), 256):
                batch = sightings[start : start + 256]
                for sighting, reading in zip(batch, reader.read([s.crop_file for s in batch]), strict=True):
                    sighting.text = reading.text
                    sighting.confidence = reading.confidence
                    sighting.unreadable = reading.unreadable
                    sighting.ctc_text = reading.ctc_text
                report("ocr", min(start + 256, len(sightings)), len(sightings))
    timings["ocr_s"] = time.perf_counter() - stage_started

    # --- stage 6: one decision per vehicle ----------------------------------------------------
    stage_started = time.perf_counter()
    for sighting in sightings:
        vehicles[sighting.track_id].sightings.append(sighting)
    for position, vehicle in enumerate(countable, start=1):
        observations = [Observation(s.text, s.confidence, s.unreadable) for s in vehicle.sightings]
        vehicle.decision = decide(observations, options.validation)
        best = best_plate_sighting(vehicle.sightings, vehicle.decision)
        vehicle.plate_crop = best.crop_file if best is not None else None
        report("validation", position, len(countable))
    settle_shared_numbers(countable)
    mark_repeat_tracks(countable)
    timings["validation_s"] = time.perf_counter() - stage_started

    # --- stage 7: annotated video and result files --------------------------------------------
    stage_started = time.perf_counter()
    files = {
        "results": out_dir / "results.json",
        "detections": out_dir / "detections.csv",
        "plates": out_dir / "plates.csv",
    }
    hidden = frozenset(vehicle.track_id for vehicle in vehicles.values() if vehicle.camera_car)
    render_details = {}
    if options.render_video:
        labels = {
            vehicle.track_id: PlateLabel(
                vehicle.decision.text, vehicle.decision.confidence, vehicle.decision.is_confirmed
            )
            for vehicle in countable
            if vehicle.decision is not None and vehicle.decision.text
        }
        min_height = options.track_rules.min_height_fraction * info.height

        def locate_plates(frame, frame_index: int, tracked: list[tuple[int, Box]]) -> dict[int, Box]:
            """Find, in this frame, the plate of each vehicle that has a number to show."""
            near = [(track_id, box) for track_id, box in tracked if box_height(box) >= min_height]
            crops = [
                (track_id, crop_region(frame, box, options.vehicle_padding, options.vehicle_padding))
                for track_id, box in near
            ]
            crops = [(track_id, crop) for track_id, crop in crops if crop is not None]
            if not crops:
                return {}
            found = detector.detect([crop.image for _, crop in crops])
            boxes = countable_boxes(frame_index)
            located: dict[int, Box] = {}
            for (track_id, crop), plates in zip(crops, found, strict=True):
                # Outline only a plate that is this vehicle's own, never a neighbour's.
                in_frame = (crop.to_frame(plate.box) for plate in plates)
                own = next((box for box in in_frame if plate_owner(box, track_id, boxes) == track_id), None)
                if own is not None:
                    located[track_id] = own
            return located

        files["annotated_video"] = out_dir / "annotated.mp4"
        render = render_annotated_video(
            info,
            run.frames,
            run.registry.class_names(),
            files["annotated_video"],
            lambda done, total: report("result_generation", done, total),
            plate_labels=labels,
            locate_plates=locate_plates,
            hidden_tracks=hidden,
        )
        render_details = {
            "render_decode_s": round(render.decode_seconds, 2),
            "render_locate_plates_s": round(render.locate_seconds, 2),
            "render_draw_s": round(render.draw_seconds, 2),
            "render_encode_s": round(render.encode_seconds, 2),
        }

    ordered = sorted(vehicles.values(), key=lambda vehicle: (vehicle.first_frame, vehicle.track_id))
    summary = summarize(ordered)
    write_detections_csv(files["detections"], info, run)
    _write_plates_csv(files["plates"], sightings, fps)
    timings["result_generation_s"] = time.perf_counter() - stage_started
    timings["total_s"] = time.perf_counter() - started
    timings = {key: round(value, 2) for key, value in timings.items()} | render_details

    document = {
        "video": {
            "file": info.path.name,
            "width": info.width,
            "height": info.height,
            "fps": str(info.fps),
            "fps_decimal": round(fps, 4),
            "frame_count": info.frame_count,
            "duration_s": round(info.duration_s, 3),
        },
        "frames_processed": run.frame_count,
        "summary": summary,
        "timings": timings,
        "speed": {
            "detect_track_fps": round(run.steady_fps, 1),
            "overall_fps": round(run.frame_count / timings["total_s"], 1),
            "times_real_time": round(run.frame_count / fps / timings["total_s"], 2),
            "ocr_ms_per_plate": round(1000 * timings["ocr_s"] / len(sightings), 1) if sightings else None,
        },
        "memory": memory_peaks(),
        "settings": tracker_details
        | {
            "plate_weights": settings.plate_weights.name,
            "plate_image_size": settings.plate_image_size,
            "plate_confidence": settings.plate_confidence,
            "plate_frames_per_track": options.plate_frames_per_track,
            "min_track_seconds": options.track_rules.min_seconds,
            "min_height_fraction": options.track_rules.min_height_fraction,
            "min_reading_confidence": options.validation.min_reading_confidence,
            "confirm_confidence": options.validation.confirm_confidence,
            "min_observations": options.validation.min_observations,
            "consensus_share": options.validation.consensus_share,
        },
        "plates_examined": len(sightings),
        "vehicles": [_vehicle_document(vehicle, fps, settings.root) for vehicle in ordered],
    }
    files["results"].write_text(json.dumps(document, indent=2), encoding="utf-8")
    report("result_generation", run.frame_count, run.frame_count)
    return PipelineResult(info, ordered, summary, timings, files, document)


def relative_path(path: Path | None, root: Path) -> str | None:
    """A path as stored in results: relative to the project root, so results can move with the project."""
    if path is None:
        return None
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _vehicle_document(vehicle: VehicleRecord, fps: float, root: Path) -> dict:
    decision = vehicle.decision
    return {
        "track_id": vehicle.track_id,
        "label": format_track_id(vehicle.track_id),
        "class": vehicle.class_name,
        "first_frame": vehicle.first_frame,
        "last_frame": vehicle.last_frame,
        "first_seen_s": round(frame_time(vehicle.first_frame, fps), 3),
        "last_seen_s": round(frame_time(vehicle.last_frame, fps), 3),
        "frames_seen": vehicle.frames_seen,
        "best_confidence": round(vehicle.best_confidence, 4),
        "countable": vehicle.countable,
        "camera_car": vehicle.camera_car,
        "same_vehicle_as": vehicle.same_vehicle_as,
        "counts_as_vehicle": vehicle.counts_as_vehicle,
        "status": vehicle.status,
        "plate": None
        if decision is None
        else {
            "text": decision.text,
            "confidence": decision.confidence,
            "support": decision.support,
            "readings": decision.readings,
            "share": decision.share,
            "reason": decision.reason,
        },
        "plates_examined": len(vehicle.sightings),
        "vehicle_crop": relative_path(vehicle.vehicle_crop, root),
        "plate_crop": relative_path(vehicle.plate_crop, root),
    }


def _write_plates_csv(path: Path, sightings: list[PlateSighting], fps: float) -> None:
    """One row per plate examined: where it was, and what the reader made of it."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["track_id", "frame", "time_s", "x1", "y1", "x2", "y2", "detector_confidence", "text", "confidence"]
            + ["unreadable", "second_decoder_text", "crop_file", "found_in_track"]
        )
        for sighting in sorted(sightings, key=lambda s: (s.track_id, s.frame)):
            writer.writerow(
                [
                    sighting.track_id,
                    sighting.frame,
                    f"{frame_time(sighting.frame, fps):.3f}",
                    *(f"{value:.1f}" for value in sighting.box),
                    f"{sighting.detector_confidence:.4f}",
                    sighting.text,
                    f"{sighting.confidence:.4f}",
                    int(sighting.unreadable),
                    sighting.ctc_text,
                    sighting.crop_file.name,
                    sighting.track_id if sighting.found_in is None else sighting.found_in,
                ]
            )
