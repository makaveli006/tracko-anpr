"""Cut vehicles and plates out of the original frame, and choose which frames to cut them from.

Crops always come from the full-resolution frame, never from a resized copy:
the plate is the smallest thing in the picture and every pixel of it counts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Box = tuple[float, float, float, float]
"""x1, y1, x2, y2 in original-frame pixels."""


@dataclass(frozen=True)
class Crop:
    """A piece of a frame, and where in the frame it came from."""

    image: np.ndarray
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def to_frame(self, box: Box) -> Box:
        """Turn a box measured inside this crop into frame coordinates."""
        x1, y1, x2, y2 = box
        return (x1 + self.x1, y1 + self.y1, x2 + self.x1, y2 + self.y1)


def crop_region(frame: np.ndarray, box: Box, pad_x: float = 0.0, pad_y: float = 0.0) -> Crop | None:
    """Cut `box` out of `frame`, optionally widened by a fraction of its size on each side.

    The region is clamped to the frame. Pixels are copied as they are, with no resizing.
    Returns None when nothing of the box lies inside the frame.
    """
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = box
    margin_x, margin_y = (x2 - x1) * pad_x, (y2 - y1) * pad_y
    left = max(0, math.floor(x1 - margin_x))
    top = max(0, math.floor(y1 - margin_y))
    right = min(width, math.ceil(x2 + margin_x))
    bottom = min(height, math.ceil(y2 + margin_y))
    if right <= left or bottom <= top:
        return None
    return Crop(frame[top:bottom, left:right].copy(), left, top, right, bottom)


def scale_box(box: Box, scale: float) -> Box:
    """The box with every coordinate multiplied by `scale`, for a frame resized by that factor."""
    x1, y1, x2, y2 = box
    return (x1 * scale, y1 * scale, x2 * scale, y2 * scale)


def box_area(box: Box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def box_inside(box: Box, frame_width: int, frame_height: int, margin: float = 2.0) -> bool:
    """True when the box does not touch the frame's edge, so the vehicle is probably not cut off."""
    x1, y1, x2, y2 = box
    return x1 > margin and y1 > margin and x2 < frame_width - margin and y2 < frame_height - margin


def best_frames(
    observations: list[tuple[int, Box]],
    frame_width: int,
    frame_height: int,
    count: int = 2,
    min_gap: int = 8,
) -> list[int]:
    """Choose the frames in which a tracked vehicle is best placed for reading its plate.

    `observations` is the track's (frame number, box) history. The vehicle is closest, and
    its plate largest, where its box is largest, so frames are taken in order of box area.
    Frames where the vehicle is cut off by the frame's edge are used only if there are no
    others. Chosen frames are kept at least `min_gap` frames apart so they are not
    near-copies of each other. Returns frame numbers, best first.
    """
    whole = [item for item in observations if box_inside(item[1], frame_width, frame_height)]
    ranked = sorted(whole or observations, key=lambda item: box_area(item[1]), reverse=True)
    chosen: list[int] = []
    for frame_index, _ in ranked:
        if len(chosen) >= count:
            break
        if all(abs(frame_index - other) >= min_gap for other in chosen):
            chosen.append(frame_index)
    return chosen
