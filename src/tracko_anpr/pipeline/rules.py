"""Rules that decide which tracks count as vehicles.

The tracker reports every box it followed, including vehicles glimpsed for a few frames,
specks in the distance, and, in dashcam footage, the camera car's own bonnet, dashboard or
cabin. "Total Vehicles" and recognition coverage are measured over the tracks that pass
these rules.

Sizes are fractions of the frame and durations are in seconds, so the rules mean the
same thing at any resolution and frame rate.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable
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
    """The camera car's bonnet: a long, wide track resting on the bottom edge of the frame."""
    cabin_seconds: float = 3.0
    cabin_width_fraction: float = 0.4
    cabin_contains_share: float = 0.1
    """The camera car's cabin, seen from inside: a very wide track with other vehicles seen through it."""


def box_height(box: Box) -> float:
    return box[3] - box[1]


def box_width(box: Box) -> float:
    return box[2] - box[0]


def box_contains(outer: Box, inner: Box, margin: float = 0.0) -> bool:
    """True when `inner` lies wholly inside `outer`, allowing `margin` pixels of slack."""
    return (
        inner[0] >= outer[0] - margin
        and inner[1] >= outer[1] - margin
        and inner[2] <= outer[2] + margin
        and inner[3] <= outer[3] + margin
    )


def is_camera_car(
    observations: list[tuple[int, Box]],
    frame_width: int,
    frame_height: int,
    fps: float,
    rules: TrackRules | None = None,
    edge_margin: float = 3.0,
    others_in_frame: Callable[[int], Iterable[Box]] | None = None,
) -> bool:
    """True when a track is part of the camera car itself, not a vehicle on the road.

    It takes two shapes. Seen over the bonnet, the car's own bodywork sits along the bottom
    of the picture for the whole journey: a long, wide track that rests on the bottom edge of
    the frame nearly all the while. A real vehicle that comes close enough to touch the bottom
    edge does so only briefly.

    Seen from inside the cabin, the detector boxes the door pillar, window and mirror as a
    "car": a track far wider than any vehicle on the road (two fifths of the frame or more)
    with other vehicles seen through it, so their whole boxes lie inside its own. A real
    vehicle ahead does not have other vehicles' boxes wholly inside it. `others_in_frame`
    gives the other tracks' boxes in a frame; without it only the bonnet shape is checked.
    """
    rules = rules or TrackRules()
    if not observations:
        return False
    seconds = len(observations) / fps
    median_width = statistics.median(box_width(box) for _, box in observations)

    if seconds >= rules.camera_car_seconds and median_width >= rules.camera_car_width_fraction * frame_width:
        at_bottom = sum(1 for _, box in observations if box[3] >= frame_height - edge_margin)
        if at_bottom / len(observations) >= rules.camera_car_bottom_share:
            return True

    if (
        others_in_frame is not None
        and seconds >= rules.cabin_seconds
        and median_width >= rules.cabin_width_fraction * frame_width
    ):
        framing = sum(
            1
            for frame, box in observations
            if any(box_contains(box, other, edge_margin) for other in others_in_frame(frame))
        )
        if framing / len(observations) >= rules.cabin_contains_share:
            return True
    return False


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
