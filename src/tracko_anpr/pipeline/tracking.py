"""Vehicle detection (YOLO26m) and tracking (TrackTrack), both through Ultralytics."""

from __future__ import annotations

import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from tracko_anpr.pipeline.video import VideoInfo, read_frames

# COCO class ids the stock YOLO26m model knows, mapped to the names shown in the product.
# "Motorcycle" is the agreed name everywhere; never "Bike".
VEHICLE_CLASSES: dict[int, str] = {2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck"}

DEFAULT_IMAGE_SIZE = 1536
DEFAULT_CONFIDENCE = 0.1
DEFAULT_LOST_SECONDS = 1.0

ProgressCallback = Callable[[int, int], None]
"""Called with (frames done, frames expected)."""


@dataclass(frozen=True)
class TrackedVehicle:
    """One tracked vehicle in one frame. The box is in original-frame pixels (x1, y1, x2, y2)."""

    track_id: int
    class_name: str
    confidence: float
    box: tuple[float, float, float, float]


def lost_track_buffer(fps: float, seconds: float = DEFAULT_LOST_SECONDS) -> int:
    """Frames a vehicle may go unseen before its track is dropped.

    TrackTrack counts this in frames and does not scale it, so it has to follow the
    video's frame rate: one second is 30 frames at 30 FPS but 60 frames at 60 FPS.
    """
    return max(1, round(fps * seconds))


def format_track_id(track_id: int) -> str:
    """Display form of a track id. Track ids are local to one processing job."""
    return f"T{track_id}"


class VehicleTracker:
    """Detects vehicles in each frame and keeps their identities from frame to frame."""

    def __init__(
        self,
        weights: str | Path,
        fps: float,
        image_size: int = DEFAULT_IMAGE_SIZE,
        confidence: float = DEFAULT_CONFIDENCE,
        lost_seconds: float = DEFAULT_LOST_SECONDS,
    ) -> None:
        # Imported here so that the rest of the package (and its tests) loads without PyTorch.
        import torch
        from ultralytics import YOLO
        from ultralytics.utils import ROOT, YAML

        weights = Path(weights)
        if not weights.is_file():
            raise FileNotFoundError(f"Vehicle weights not found: {weights}. See 'Model Files' in ARCHITECTURE.md.")

        self.on_gpu = torch.cuda.is_available()
        self.image_size = image_size
        self.confidence = confidence
        self.track_buffer = lost_track_buffer(fps, lost_seconds)
        self.model = YOLO(str(weights))

        # Ultralytics ships TrackTrack; take its defaults and only set the lost-track time for this frame rate.
        config = YAML.load(ROOT / "cfg" / "trackers" / "tracktrack.yaml")
        config["track_buffer"] = self.track_buffer
        handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", prefix="tracktrack_", delete=False)  # noqa: SIM115
        handle.close()
        self._tracker_config = Path(handle.name)
        YAML.save(self._tracker_config, config)

        self._options: dict = {
            "persist": True,  # keep tracker state between calls: the frames are one continuous video
            "tracker": str(self._tracker_config),
            "classes": list(VEHICLE_CLASSES),
            "imgsz": image_size,
            "conf": confidence,
            "device": 0 if self.on_gpu else "cpu",
            "verbose": False,
        }
        if self.on_gpu:
            self._options["quantize"] = 16  # FP16 where supported; replaces the deprecated `half=True`
            torch.cuda.reset_peak_memory_stats()

    @property
    def precision(self) -> str:
        return "FP16" if self.on_gpu else "FP32"

    def update(self, frame: np.ndarray) -> list[TrackedVehicle]:
        """Process the next frame of the video and return the vehicles being tracked in it."""
        result = self.model.track(frame, **self._options)[0]

        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return []

        vehicles = []
        for track_id, class_id, confidence, box in zip(
            boxes.id.int().tolist(), boxes.cls.int().tolist(), boxes.conf.tolist(), boxes.xyxy.tolist(), strict=True
        ):
            class_name = VEHICLE_CLASSES.get(class_id)
            if class_name is None:
                continue
            vehicles.append(TrackedVehicle(track_id, class_name, float(confidence), tuple(box)))
        return vehicles

    def detect(self, frame: np.ndarray) -> list[TrackedVehicle]:
        """The vehicles in one frame on its own, without tracking (track id -1): for sampling checks."""
        options = {key: value for key, value in self._options.items() if key not in ("persist", "tracker")}
        boxes = self.model.predict(frame, **options)[0].boxes
        if boxes is None:
            return []
        found = []
        for class_id, confidence, box in zip(
            boxes.cls.int().tolist(), boxes.conf.tolist(), boxes.xyxy.tolist(), strict=True
        ):
            class_name = VEHICLE_CLASSES.get(class_id)
            if class_name is not None:
                found.append(TrackedVehicle(-1, class_name, float(confidence), tuple(box)))
        return found

    def close(self) -> None:
        self._tracker_config.unlink(missing_ok=True)

    def __enter__(self) -> VehicleTracker:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


@dataclass
class TrackSummary:
    """Everything seen about one track across the video."""

    track_id: int
    first_frame: int
    last_frame: int
    frames_seen: int = 0
    best_confidence: float = 0.0
    class_scores: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    @property
    def class_name(self) -> str:
        """The track's vehicle type: the class with the most confidence-weighted votes."""
        return max(self.class_scores.items(), key=lambda item: item[1])[0]


class TrackRegistry:
    """Collects per-track facts as frames go by.

    The detector can label the same vehicle differently from one frame to the next
    (a van as "Car", then "Truck"). The registry settles each track on its most
    supported class, so the label drawn on the video does not flicker.
    """

    def __init__(self) -> None:
        self.tracks: dict[int, TrackSummary] = {}

    def update(self, frame_index: int, vehicles: list[TrackedVehicle]) -> None:
        for vehicle in vehicles:
            summary = self.tracks.get(vehicle.track_id)
            if summary is None:
                summary = TrackSummary(vehicle.track_id, first_frame=frame_index, last_frame=frame_index)
                self.tracks[vehicle.track_id] = summary
            summary.last_frame = frame_index
            summary.frames_seen += 1
            summary.best_confidence = max(summary.best_confidence, vehicle.confidence)
            summary.class_scores[vehicle.class_name] += vehicle.confidence

    def class_names(self) -> dict[int, str]:
        """Settled class for every track id."""
        return {track_id: summary.class_name for track_id, summary in self.tracks.items()}

    def counts_by_class(self) -> dict[str, int]:
        counts = dict.fromkeys(VEHICLE_CLASSES.values(), 0)
        for summary in self.tracks.values():
            counts[summary.class_name] += 1
        return counts


@dataclass
class CameraPath:
    """How far the picture has moved since the first frame, measured from every few frames.

    Phone footage is rarely still, so a parked vehicle drifts across the picture. Subtracting this
    position from a box gives where the vehicle is relative to the scene. It feeds only the
    repeat-track rule (pipeline/repeats.py); detection and tracking do not use it.
    """

    step: int = 6
    width: int = 480
    min_response: float = 0.05
    """A weaker match than this between two samples is ignored rather than trusted."""
    positions: dict[int, tuple[float, float]] = field(default_factory=dict)
    _previous: np.ndarray | None = None
    _position: tuple[float, float] = (0.0, 0.0)

    def record(self, frame_index: int, frame: np.ndarray) -> None:
        if frame_index % self.step:
            return
        scale = frame.shape[1] / self.width
        small = cv2.resize(frame, (self.width, round(frame.shape[0] / scale)), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        if self._previous is not None:
            (shift_x, shift_y), response = cv2.phaseCorrelate(self._previous, gray)
            if response > self.min_response:
                self._position = (self._position[0] + shift_x * scale, self._position[1] + shift_y * scale)
        self._previous = gray
        self.positions[frame_index] = self._position

    def at(self, frame_index: int) -> tuple[float, float]:
        """The camera's position at a frame, in original-frame pixels."""
        return self.positions.get(frame_index - frame_index % self.step, (0.0, 0.0))


@dataclass
class TrackingRun:
    """Result of the detection-and-tracking pass over one video."""

    frames: list[list[TrackedVehicle]]
    """Tracked vehicles for each frame, in order; index is the frame number."""
    registry: TrackRegistry
    decode_seconds: float
    track_seconds: float
    warmup_seconds: float = 0.0
    """Time spent on the first frame, which includes one-off GPU start-up and is not typical."""
    camera: CameraPath = field(default_factory=CameraPath)
    camera_seconds: float = 0.0

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def steady_fps(self) -> float:
        """Detection-and-tracking speed once warmed up, in frames per second."""
        steady_seconds = self.track_seconds - self.warmup_seconds
        if self.frame_count < 2 or steady_seconds <= 0:
            return 0.0
        return (self.frame_count - 1) / steady_seconds


def track_video(
    info: VideoInfo,
    tracker: VehicleTracker,
    max_frames: int | None = None,
    progress: ProgressCallback | None = None,
) -> TrackingRun:
    """Run detection and tracking over a video, keeping every frame's boxes for the later passes."""
    expected = info.frame_count if max_frames is None else min(info.frame_count, max_frames)
    frames: list[list[TrackedVehicle]] = []
    registry = TrackRegistry()
    decode_seconds = track_seconds = warmup_seconds = camera_seconds = 0.0
    camera = CameraPath()

    source = read_frames(info.path, max_frames)
    while True:
        started = time.perf_counter()
        frame = next(source, None)
        decode_seconds += time.perf_counter() - started
        if frame is None:
            break

        started = time.perf_counter()
        camera.record(len(frames), frame)
        camera_seconds += time.perf_counter() - started

        started = time.perf_counter()
        vehicles = tracker.update(frame)
        spent = time.perf_counter() - started
        track_seconds += spent
        if not frames:
            warmup_seconds = spent

        registry.update(len(frames), vehicles)
        frames.append(vehicles)
        if progress is not None:
            progress(len(frames), expected)

    return TrackingRun(frames, registry, decode_seconds, track_seconds, warmup_seconds, camera, camera_seconds)
