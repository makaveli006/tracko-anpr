"""Which way a tracked vehicle travelled, from its boxes alone.

The cameras are static, so a vehicle coming nearer gets taller in the picture and one going away
gets shorter; sideways travel moves the box across the frame. The first and last part of the
track are compared by their medians, because the tracker's first and last boxes are the noisiest
(the vehicle is entering or leaving the frame). Nothing here depends on resolution or frame rate:
heights are compared as a ratio and sideways movement as a share of the frame width.

The thresholds are not part of the pipeline settings frozen in Phase 7: changing them changes
only the direction labels, never a count or a plate. No model runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from tracko_anpr.pipeline.cropping import Box

TOWARDS = "towards"
AWAY = "away"
LEFT = "left"
RIGHT = "right"


@dataclass(frozen=True)
class DirectionRules:
    approach_ratio: float = 1.25
    """Box height at the end over the start: at least this → towards the camera; at most 1/this → away."""
    sideways_fraction: float = 0.10
    """The box centre must move at least this share of the frame width to count as left or right."""
    sample_share: float = 0.2
    """The first and last fifth of a track's boxes are compared (by their medians)."""
    min_samples: int = 3
    """Each end uses at least this many boxes; shorter tracks compare their two halves."""


@dataclass(frozen=True)
class Direction:
    """A vehicle's travel direction relative to the picture; either part may be unknown."""

    approach: str | None = None
    """'towards' (the camera) or 'away' (from it), or None when its size hardly changed."""
    sideways: str | None = None
    """'left' or 'right' across the picture, or None when it hardly moved sideways."""

    @property
    def label(self) -> str:
        return direction_label(self.approach, self.sideways)


def direction_label(approach: str | None, sideways: str | None) -> str:
    """The words the dashboard uses: 'Towards camera', 'Away from camera, left', 'Right', 'Undetermined'."""
    first = {TOWARDS: "Towards camera", AWAY: "Away from camera"}.get(approach or "")
    if first and sideways:
        return f"{first}, {sideways}"
    if first:
        return first
    if sideways:
        return sideways.capitalize()
    return "Undetermined"


def short_direction(approach: str | None, sideways: str | None) -> str:
    """The table's short form: 'Towards', 'Away, left', 'Left', or an em dash."""
    first = {TOWARDS: "Towards", AWAY: "Away"}.get(approach or "")
    if first and sideways:
        return f"{first}, {sideways}"
    return first or (sideways.capitalize() if sideways else "—")


def travel_direction(
    observations: list[tuple[int, Box]], frame_width: int, rules: DirectionRules | None = None
) -> Direction:
    """The direction a track travelled, from its (frame, box) observations in frame order."""
    rules = rules or DirectionRules()
    boxes = [box for _, box in sorted(observations, key=lambda item: item[0])]
    if len(boxes) < 2 or frame_width <= 0:
        return Direction()
    count = max(rules.min_samples, round(len(boxes) * rules.sample_share))
    count = min(count, len(boxes) // 2)  # never let the two ends overlap
    first, last = boxes[:count], boxes[-count:]

    height_start = median(box[3] - box[1] for box in first)
    height_end = median(box[3] - box[1] for box in last)
    approach = None
    if height_start > 0 and height_end > 0:
        ratio = height_end / height_start
        if ratio >= rules.approach_ratio:
            approach = TOWARDS
        elif ratio <= 1 / rules.approach_ratio:
            approach = AWAY

    centre_start = median((box[0] + box[2]) / 2 for box in first)
    centre_end = median((box[0] + box[2]) / 2 for box in last)
    shift = (centre_end - centre_start) / frame_width
    sideways = None
    if shift >= rules.sideways_fraction:
        sideways = RIGHT
    elif shift <= -rules.sideways_fraction:
        sideways = LEFT
    return Direction(approach, sideways)
