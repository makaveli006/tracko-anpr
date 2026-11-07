"""Draw vehicle boxes, tracking labels and number plates, and render the annotated video.

Colours follow DESIGN/DASHBOARD_DESIGN.md: bright green vehicle outlines with dark green
labels and white text (white on bright green is too hard to read), and amber for number
plates. OpenCV uses blue-green-red order.

Rendering is a pass of its own, run after tracking and validation have finished, so every
label shows what is known about the whole track: its settled class, and its registration
number only as far as validation supports it.

The plate outlines come from the plates found in stage 4, not from running the plate detector
again: a plate sits still on its vehicle, so its place in the frames between the examined ones
is interpolated from its position relative to the vehicle box (`plate_boxes_by_frame`). The
annotated copy is scaled down to `max_height` when the input is taller (4K is played in the
browser at a fraction of its size anyway, and encoding it costs minutes), so every box is scaled
with the frame; the original video is never touched.
"""

from __future__ import annotations

import bisect
import time
from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np

from tracko_anpr.pipeline.cropping import Box, scale_box
from tracko_anpr.pipeline.tracking import ProgressCallback, TrackedVehicle, format_track_id
from tracko_anpr.pipeline.video import FFmpegWriter, VideoInfo, read_frames

VEHICLE_BOX_COLOR = (40, 212, 54)  # #36D428
LABEL_BACKGROUND = (34, 101, 22)  # #166522
LABEL_TEXT_COLOR = (255, 255, 255)
PLATE_COLOR = (21, 204, 250)  # #FACC15, amber
PLATE_TEXT_ON_AMBER = (20, 20, 20)
UNCONFIRMED_BACKGROUND = (40, 40, 40)
_FONT = cv2.FONT_HERSHEY_SIMPLEX

PlateBoxesByFrame = dict[int, dict[int, Box]]
"""Frame index -> track id -> where that vehicle's plate is in the frame, in the frame's pixels."""

Fractions = tuple[float, float, float, float]
"""A plate box relative to its vehicle's box: (left, top, width, height) as fractions of the vehicle box."""


@dataclass(frozen=True)
class PlateLabel:
    """What to write beside a vehicle's number plate."""

    text: str
    confidence: float
    confirmed: bool


def format_vehicle_label(track_id: int, class_name: str, confidence: float) -> str:
    """Text shown above a vehicle, for example '#T101 Car (0.98)'."""
    return f"#{format_track_id(track_id)} {class_name} ({confidence:.2f})"


def format_plate_label(label: PlateLabel) -> str:
    """Text shown at a plate: 'KL10AB1234 (0.97)' once confirmed, otherwise marked as unconfirmed."""
    if label.confirmed:
        return f"{label.text} ({label.confidence:.2f})"
    return f"{label.text} unconfirmed"


@dataclass(frozen=True)
class _Style:
    """Line and text sizes for a frame, scaled so 1080p and 2K look alike."""

    line: int
    font_scale: float
    font_line: int
    pad: int

    @classmethod
    def for_frame(cls, frame: np.ndarray) -> _Style:
        scale = frame.shape[0] / 1080
        return cls(max(2, round(2 * scale)), 0.6 * scale, max(1, round(1.5 * scale)), max(3, round(4 * scale)))


def _label_size(text: str, style: _Style) -> tuple[int, int, int]:
    (text_width, text_height), baseline = cv2.getTextSize(text, _FONT, style.font_scale, style.font_line)
    return text_width + 2 * style.pad, text_height + baseline + 2 * style.pad, text_height


def _draw_label(frame: np.ndarray, text: str, left: int, top: int, background, foreground, style: _Style) -> None:
    """Draw a filled label with its top-left corner at (left, top), moved as needed to stay inside the frame."""
    height, width = frame.shape[:2]
    box_width, box_height, text_height = _label_size(text, style)
    left = min(max(left, 0), max(0, width - box_width))
    top = min(max(top, 0), max(0, height - box_height))
    cv2.rectangle(frame, (left, top), (left + box_width, top + box_height), background, cv2.FILLED)
    cv2.putText(
        frame,
        text,
        (left + style.pad, top + style.pad + text_height),
        _FONT,
        style.font_scale,
        foreground,
        style.font_line,
        cv2.LINE_AA,
    )


def draw_vehicles(frame: np.ndarray, vehicles: list[TrackedVehicle], class_names: dict[int, str]) -> None:
    """Draw every tracked vehicle onto the frame, in place.

    `class_names` gives the settled class for each track id, which may differ
    from the detector's guess for this single frame.
    """
    style = _Style.for_frame(frame)
    for vehicle in vehicles:
        x1, y1, x2, y2 = (round(value) for value in vehicle.box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), VEHICLE_BOX_COLOR, style.line)
        class_name = class_names.get(vehicle.track_id, vehicle.class_name)
        label = format_vehicle_label(vehicle.track_id, class_name, vehicle.confidence)
        _, label_height, _ = _label_size(label, style)
        # Sit the label on top of the box; if that would leave the frame, it is moved inside.
        _draw_label(frame, label, x1, y1 - label_height, LABEL_BACKGROUND, LABEL_TEXT_COLOR, style)


def draw_plates(
    frame: np.ndarray,
    vehicles: list[TrackedVehicle],
    plate_labels: dict[int, PlateLabel],
    plate_boxes: dict[int, Box],
) -> None:
    """Draw the number plate of every vehicle that has one to show, in place.

    Where the plate was located in this frame it gets an amber outline with the number just
    below it. Where it was not (too far, hidden), the number is written inside the bottom of
    the vehicle's box instead, so the vehicle keeps its number all the way through.
    A confirmed number is black on amber; an unconfirmed one is amber on dark and says so.
    """
    style = _Style.for_frame(frame)
    for vehicle in vehicles:
        label = plate_labels.get(vehicle.track_id)
        if label is None:
            continue
        text = format_plate_label(label)
        background, foreground = (
            (PLATE_COLOR, PLATE_TEXT_ON_AMBER) if label.confirmed else (UNCONFIRMED_BACKGROUND, PLATE_COLOR)
        )
        plate_box = plate_boxes.get(vehicle.track_id)
        if plate_box is not None:
            x1, y1, x2, y2 = (round(value) for value in plate_box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), PLATE_COLOR, style.line)
            _draw_label(frame, text, x1, y2 + style.line, background, foreground, style)
        else:
            _, label_height, _ = _label_size(text, style)
            left, bottom = round(vehicle.box[0]) + style.line, round(vehicle.box[3]) - style.line
            _draw_label(frame, text, left, bottom - label_height, background, foreground, style)


def plate_boxes_by_frame(
    frames: list[list[TrackedVehicle]],
    sightings: dict[int, list[tuple[int, Box]]],
    min_height: float = 0.0,
) -> PlateBoxesByFrame:
    """Where each vehicle's plate is in every frame, from the frames where it was actually found.

    `sightings` maps a track id to the (frame index, plate box) pairs found for it in stage 4.
    A plate keeps its place on its vehicle, so in every other frame of the track the box is
    placed by its position relative to the vehicle's box: the fractions (left, top, width,
    height) are interpolated linearly between the two nearest sighted frames and held constant
    before the first and after the last. Frames where the vehicle box is under `min_height`
    pixels tall get no plate box, as the plate would be too small to outline. No model runs.
    """
    vehicle_boxes: dict[int, list[tuple[int, Box]]] = {track_id: [] for track_id in sightings}
    for frame_index, vehicles in enumerate(frames):
        for vehicle in vehicles:
            if vehicle.track_id in vehicle_boxes:
                vehicle_boxes[vehicle.track_id].append((frame_index, vehicle.box))

    located: PlateBoxesByFrame = {}
    for track_id, found in sightings.items():
        by_frame = dict(vehicle_boxes[track_id])
        keyed: list[tuple[int, Fractions]] = []
        for frame_index, plate in sorted(found):
            vehicle_box = by_frame.get(frame_index)
            if vehicle_box is not None:
                keyed.append((frame_index, _relative_box(plate, vehicle_box)))
        if not keyed:
            continue
        for frame_index, vehicle_box in vehicle_boxes[track_id]:
            if vehicle_box[3] - vehicle_box[1] < min_height:
                continue
            fractions = _fractions_at(frame_index, keyed)
            located.setdefault(frame_index, {})[track_id] = _absolute_box(fractions, vehicle_box)
    return located


def _relative_box(plate: Box, vehicle: Box) -> Fractions:
    width = max(vehicle[2] - vehicle[0], 1e-6)
    height = max(vehicle[3] - vehicle[1], 1e-6)
    return (
        (plate[0] - vehicle[0]) / width,
        (plate[1] - vehicle[1]) / height,
        (plate[2] - plate[0]) / width,
        (plate[3] - plate[1]) / height,
    )


def _absolute_box(fractions: Fractions, vehicle: Box) -> Box:
    width = vehicle[2] - vehicle[0]
    height = vehicle[3] - vehicle[1]
    left = vehicle[0] + fractions[0] * width
    top = vehicle[1] + fractions[1] * height
    return (left, top, left + fractions[2] * width, top + fractions[3] * height)


def _fractions_at(frame_index: int, keyed: list[tuple[int, Fractions]]) -> Fractions:
    """The plate's relative position at a frame: held outside the sighted span, interpolated inside it."""
    position = bisect.bisect_right([frame for frame, _ in keyed], frame_index)
    if position == 0:
        return keyed[0][1]
    if position == len(keyed):
        return keyed[-1][1]
    (frame_before, before), (frame_after, after) = keyed[position - 1], keyed[position]
    weight = (frame_index - frame_before) / (frame_after - frame_before)
    left, top, width, height = (b + (a - b) * weight for b, a in zip(before, after, strict=True))
    return (left, top, width, height)


def output_size(width: int, height: int, max_height: int | None) -> tuple[int, int, float]:
    """The annotated copy's size and the factor it is scaled by: the input's, unless taller than `max_height`."""
    if max_height is None or height <= max_height:
        return width, height, 1.0
    scale = max_height / height
    scaled_width = max(2, round(width * scale) // 2 * 2)  # H.264 wants even sizes
    return scaled_width, max_height, scale


@dataclass
class RenderRun:
    """Result of rendering one annotated video."""

    output: Path
    frame_count: int
    decode_seconds: float
    draw_seconds: float
    encode_seconds: float
    width: int = 0
    height: int = 0


def render_annotated_video(
    info: VideoInfo,
    frames: list[list[TrackedVehicle]],
    class_names: dict[int, str],
    output: str | Path,
    progress: ProgressCallback | None = None,
    plate_labels: dict[int, PlateLabel] | None = None,
    plate_boxes: PlateBoxesByFrame | None = None,
    hidden_tracks: frozenset[int] = frozenset(),
    max_height: int | None = None,
) -> RenderRun:
    """Write the annotated copy of a video: same frame rate and frame count as the frames given.

    `frames[i]` holds the vehicles tracked in frame `i`. Tracks in `hidden_tracks` are not drawn.
    Vehicles with an entry in `plate_labels` get their number, outlined where `plate_boxes` says
    their plate is (see `plate_boxes_by_frame`). When the input is taller than `max_height` the
    copy is scaled down to that height, boxes included; otherwise it keeps the input's size.
    Audio is copied from the original.
    """
    output = Path(output)
    plate_labels = plate_labels or {}
    plate_boxes = plate_boxes or {}
    decode_seconds = draw_seconds = encode_seconds = 0.0
    written = 0
    width, height, scale = output_size(info.width, info.height, max_height)

    audio_seconds = len(frames) / info.fps_float  # no more audio than the frames being written
    with FFmpegWriter(output, width, height, info.fps, audio_source=info.path, audio_seconds=audio_seconds) as writer:
        source = read_frames(info.path, max_frames=len(frames))
        while True:
            started = time.perf_counter()
            frame = next(source, None)
            decode_seconds += time.perf_counter() - started
            if frame is None:
                break

            started = time.perf_counter()
            vehicles = [vehicle for vehicle in frames[written] if vehicle.track_id not in hidden_tracks]
            boxes = plate_boxes.get(written, {})
            if scale != 1.0:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                vehicles = [replace(vehicle, box=scale_box(vehicle.box, scale)) for vehicle in vehicles]
                boxes = {track_id: scale_box(box, scale) for track_id, box in boxes.items()}
            draw_vehicles(frame, vehicles, class_names)
            draw_plates(frame, vehicles, plate_labels, boxes)
            draw_seconds += time.perf_counter() - started

            started = time.perf_counter()
            writer.write(frame)
            encode_seconds += time.perf_counter() - started

            written += 1
            if progress is not None:
                progress(written, len(frames))

        started = time.perf_counter()
    encode_seconds += time.perf_counter() - started  # time FFmpeg takes to finish the file after the last frame

    return RenderRun(output, written, decode_seconds, draw_seconds, encode_seconds, width, height)
