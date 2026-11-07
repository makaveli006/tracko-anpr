"""The plate-size check: are the number plates in this video big enough to read?

Plate width in pixels is the best single predictor of recognition coverage (RECORDING_GUIDE.md:
at least 130 px when the vehicle is closest, almost nothing under 60 px). Before a full run,
which takes minutes, this samples a few frames spread over the video, finds the vehicles and
their plates with the same two detectors the pipeline uses, and reports how wide the plates
are. It measures size only: blur, angle and light are not checked, and nothing it finds is
stored as a result. Inspired by the pixel counter in Axis's licence plate guidance.

The verdict is built on the largest plates seen (the 90th percentile), not the median: a plate
is only big when its vehicle is close, and that is the moment the pipeline reads it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import median

from tracko_anpr.config import Settings
from tracko_anpr.pipeline.cropping import crop_region
from tracko_anpr.pipeline.rules import TrackRules
from tracko_anpr.pipeline.video import VideoInfo, probe_video, read_frames_at

GOOD_WIDTH = 130
"""Plates this wide or wider are read most of the time (the recording guide's figure)."""
POOR_WIDTH = 60
"""Under this width almost nothing is read."""
DEFAULT_FRAMES = 24
VEHICLE_PADDING = 0.04
"""Margin around a vehicle box when it is cut out: the same as the pipeline's stage 4."""

GOOD, BORDERLINE, LOW, NO_PLATES, NO_VEHICLES = "good", "borderline", "low", "no_plates", "no_vehicles"


@dataclass(frozen=True)
class PlateCheck:
    """What the check found; stored on the video and shown on the Upload page."""

    frames_sampled: int
    vehicles_seen: int
    """Vehicle boxes at least as tall as the pipeline's minimum (6% of the frame), over all sampled frames."""
    plates_seen: int
    median_width_px: int | None
    largest_width_px: int | None
    """The 90th percentile of the plate widths: how wide plates get when a vehicle is close."""
    share_under_60: float | None
    share_over_130: float | None
    verdict: str
    """good | borderline | low | no_plates | no_vehicles"""
    message: str
    """One sentence for the user."""

    def as_dict(self) -> dict:
        return asdict(self)


def sample_frame_numbers(frame_count: int, count: int = DEFAULT_FRAMES) -> list[int]:
    """`count` frame numbers spread evenly over the video, leaving out the first and last 5%."""
    if frame_count <= 0 or count <= 0:
        return []
    first = int(frame_count * 0.05)
    last = max(first, int(frame_count * 0.95) - 1)
    count = min(count, last - first + 1)
    if count <= 1:
        return [(first + last) // 2]
    step = (last - first) / (count - 1)
    return sorted({first + round(index * step) for index in range(count)})


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[round(share * (len(ordered) - 1))]


def summarise(widths: list[float], vehicles_seen: int, frames_sampled: int) -> PlateCheck:
    """Turn the plate widths found into figures and a verdict. Pure, so it is tested without a model."""
    if vehicles_seen == 0:
        return PlateCheck(
            frames_sampled, 0, 0, None, None, None, None, NO_VEHICLES,
            f"No vehicles were found in the {frames_sampled} sampled frames. The full run may still find some, "
            "but check that the camera sees the road.",
        )  # fmt: skip
    if not widths:
        return PlateCheck(
            frames_sampled, vehicles_seen, 0, None, None, None, None, NO_PLATES,
            f"{vehicles_seen} vehicles were seen in the {frames_sampled} sampled frames but no number plate was "
            "found on them: plates may be too small, hidden or seen from the side.",
        )  # fmt: skip
    typical = round(median(widths))
    largest = round(percentile(widths, 0.9))
    under = sum(1 for width in widths if width < POOR_WIDTH) / len(widths)
    over = sum(1 for width in widths if width >= GOOD_WIDTH) / len(widths)
    sizes = (
        f"Largest plates about {largest} px wide (median {typical} px) across {vehicles_seen} vehicles "
        f"in {frames_sampled} sampled frames"
    )
    if largest >= GOOD_WIDTH:
        verdict, outcome = GOOD, "most of them should be read."
    elif largest >= POOR_WIDTH:
        verdict, outcome = BORDERLINE, "some will be read; closer or zoomed-in footage would read more."
    else:
        verdict, outcome = LOW, "expect few numbers to be read. Move closer or zoom in (see the recording tips)."
    return PlateCheck(
        frames_sampled, vehicles_seen, len(widths), typical, largest, round(under, 3), round(over, 3), verdict,
        f"{sizes}: {outcome}",
    )  # fmt: skip


def check_video_file(
    path, settings: Settings, models: CheckModels | None = None, count: int = DEFAULT_FRAMES
) -> PlateCheck:
    """`check_plate_sizes` for a file on disk: probes it first (a missing or broken file raises VideoError)."""
    return check_plate_sizes(probe_video(path), settings, models, count)


class CheckModels:
    """The two detectors the check needs, loaded once so a worker can serve many checks."""

    def __init__(self, settings: Settings) -> None:
        from tracko_anpr.pipeline.plates import PlateDetector
        from tracko_anpr.pipeline.tracking import VehicleTracker

        # The tracker's lost-track time depends on the frame rate; detection alone does not use it.
        self.tracker = VehicleTracker(
            settings.vehicle_weights, 30.0, settings.vehicle_image_size, settings.vehicle_confidence
        )
        self.detector = PlateDetector(settings.plate_weights, settings.plate_image_size, settings.plate_confidence)

    def close(self) -> None:
        self.tracker.close()


def check_plate_sizes(
    info: VideoInfo, settings: Settings, models: CheckModels | None = None, count: int = DEFAULT_FRAMES
) -> PlateCheck:
    """Sample the video, find vehicles and plates in the samples, and report the plate widths."""
    own_models = models is None
    models = models or CheckModels(settings)
    min_height = TrackRules().min_height_fraction * info.height
    widths: list[float] = []
    vehicles_seen = frames_sampled = 0
    try:
        for _, frame in read_frames_at(info.path, sample_frame_numbers(info.frame_count, count)):
            frames_sampled += 1
            boxes = [
                vehicle.box for vehicle in models.tracker.detect(frame) if vehicle.box[3] - vehicle.box[1] >= min_height
            ]
            crops = [
                crop for crop in (crop_region(frame, box, VEHICLE_PADDING, VEHICLE_PADDING) for box in boxes) if crop
            ]
            vehicles_seen += len(crops)
            if not crops:
                continue
            for plates in models.detector.detect([crop.image for crop in crops]):
                if plates:
                    widths.append(max(plate.width for plate in plates))  # crops keep original pixels
    finally:
        if own_models:
            models.close()
    return summarise(widths, vehicles_seen, frames_sampled)
