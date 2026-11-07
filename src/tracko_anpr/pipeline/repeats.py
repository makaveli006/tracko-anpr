"""Parked vehicles seen again: tracks that are one vehicle, found without a number plate.

The tracker loses a parked vehicle each time traffic passes in front of it and gives it a new
id when it reappears, so one scooter was counted 19 times. Tracks are the same parked vehicle
when both barely moved, they never overlap in time, their boxes cover the same place once
the camera's own movement is taken out, and they look alike (colour of the vehicle's cut-out).

This reduces the overcount; it does not remove it. Tested against hand labels on 2026-11-07:
`kdy` went from 167 entries to 124 for 87 real vehicles, with 2 vehicles wrongly merged, and
`zoomed-in` from 59 to 42 for 32, with none. Looser thresholds wrongly merge real vehicles,
which then vanish from the count, so they stay strict. See ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from tracko_anpr.pipeline.cropping import Box


@dataclass(frozen=True)
class ParkedRules:
    max_move: float = 0.05
    """A track may drift this share of the frame width and still count as parked."""
    min_overlap: float = 0.5
    """Overlap (intersection over union) of the two boxes once the camera's movement is removed."""
    min_look: float = 0.6
    """Correlation of the colour histograms of the two vehicle cut-outs."""


@dataclass
class ParkedTrack:
    track_id: int
    first_frame: int
    last_frame: int
    box: Box
    """The median box of the track, with the camera's movement removed."""
    drift: float
    """How far the track moved across the picture, as a share of the frame width."""
    look: np.ndarray | None = None
    number: str | None = None
    """Its confirmed number, if it has one."""


@dataclass
class _Group:
    tracks: list[ParkedTrack] = field(default_factory=list)

    @property
    def numbers(self) -> set[str]:
        return {track.number for track in self.tracks if track.number}

    def overlaps_in_time(self, other: _Group) -> bool:
        return any(
            a.first_frame <= b.last_frame and b.first_frame <= a.last_frame for a in self.tracks for b in other.tracks
        )


def overlap(a: Box, b: Box) -> float:
    """Intersection over union of two boxes."""
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    shared = max(0.0, width) * max(0.0, height)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - shared
    return shared / union if union > 0 else 0.0


def colour_look(image: np.ndarray) -> np.ndarray:
    """A vehicle cut-out's colours as a normalised hue and saturation histogram."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
    return cv2.normalize(histogram, histogram)


def looks_alike(a: np.ndarray | None, b: np.ndarray | None, minimum: float) -> bool:
    if a is None or b is None:
        return False
    return cv2.compareHist(a, b, cv2.HISTCMP_CORREL) >= minimum


def parked_groups(tracks: list[ParkedTrack], rules: ParkedRules | None = None) -> list[list[ParkedTrack]]:
    """Groups of two or more tracks that are one parked vehicle, each in order of appearance.

    A group never holds two tracks in view at the same time, because one vehicle cannot be in two
    places at once, and never holds two different confirmed numbers.
    """
    rules = rules or ParkedRules()
    still = sorted((t for t in tracks if t.drift < rules.max_move), key=lambda t: (t.first_frame, t.track_id))
    group_of = {track.track_id: _Group([track]) for track in still}
    for position, a in enumerate(still):
        for b in still[position + 1 :]:
            first, second = group_of[a.track_id], group_of[b.track_id]
            if first is second or first.overlaps_in_time(second) or len(first.numbers | second.numbers) > 1:
                continue
            if overlap(a.box, b.box) >= rules.min_overlap and looks_alike(a.look, b.look, rules.min_look):
                first.tracks.extend(second.tracks)
                for track in second.tracks:
                    group_of[track.track_id] = first
    distinct = {id(group): group for group in group_of.values()}.values()
    found = [sorted(g.tracks, key=lambda t: (t.first_frame, t.track_id)) for g in distinct if len(g.tracks) > 1]
    return sorted(found, key=lambda group: group[0].first_frame)
