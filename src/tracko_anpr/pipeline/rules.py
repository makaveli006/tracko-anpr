"""Rules that decide which tracks count as vehicles.

The tracker reports every box it followed, including vehicles glimpsed for a few frames,
specks in the distance, and, in dashcam footage, the camera car's own bonnet or dashboard.
"Total Vehicles" and recognition coverage are measured over the tracks that pass these rules.

Sizes are fractions of the frame and durations are in seconds, so the rules mean the
same thing at any resolution and frame rate.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from tracko_anpr.pipeline.cropping import Box


@dataclass(frozen=True)
class TrackRules:
    min_seconds: float = 0.5
    """A vehicle must be followed for at least this long to count."""
    min_height_fraction: float = 0.06
    """...and at some point be at least this tall, as a fraction of the frame height (65 px at 1080p)."""
    camera_car_seconds: float = 10.0
    camera_car_bottom_share: float = 0.8
    camera_car_width_fraction: float = 0.25


def box_height(box: Box) -> float:
    return box[3] - box[1]


def box_width(box: Box) -> float:
    return box[2] - box[0]


def is_camera_car(
    observations: list[tuple[int, Box]],
    frame_width: int,
    frame_height: int,
    fps: float,
    rules: TrackRules | None = None,
    edge_margin: float = 3.0,
) -> bool:
    """True when a track is the camera car's own bonnet or dashboard, not a vehicle on the road.

    Seen from inside a car, its own bodywork sits along the bottom of the picture for the whole
    journey. A track is taken for that when it lasts a long time, is wide, and rests on the
    bottom edge of the frame nearly all the while. A real vehicle that comes close enough to
    touch the bottom edge does so only briefly.
    """
    rules = rules or TrackRules()
    if not observations:
        return False
    if len(observations) / fps < rules.camera_car_seconds:
        return False
    at_bottom = sum(1 for _, box in observations if box[3] >= frame_height - edge_margin)
    if at_bottom / len(observations) < rules.camera_car_bottom_share:
        return False
    return statistics.median(box_width(box) for _, box in observations) >= rules.camera_car_width_fraction * frame_width


def is_countable(
    observations: list[tuple[int, Box]],
    frame_height: int,
    fps: float,
    rules: TrackRules | None = None,
) -> bool:
    """True when a track was followed long enough, and came near enough, to count as a vehicle."""
    rules = rules or TrackRules()
    if not observations:
        return False
    if len(observations) / fps < rules.min_seconds:
        return False
    return max(box_height(box) for _, box in observations) >= rules.min_height_fraction * frame_height
