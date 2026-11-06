"""Draw vehicle boxes and tracking labels, and render the annotated video.

Colours follow DESIGN/DASHBOARD_DESIGN.md: bright green box outlines, and
dark green label backgrounds with white text (white on bright green is too
hard to read). OpenCV uses blue-green-red order.

Rendering is a pass of its own, run after tracking has finished, so every
label can show what is known about the whole track rather than a guess made
partway through.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from tracko_anpr.pipeline.tracking import ProgressCallback, TrackedVehicle, format_track_id
from tracko_anpr.pipeline.video import FFmpegWriter, VideoInfo, read_frames

VEHICLE_BOX_COLOR = (40, 212, 54)  # #36D428
LABEL_BACKGROUND = (34, 101, 22)  # #166522
LABEL_TEXT_COLOR = (255, 255, 255)
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def format_vehicle_label(track_id: int, class_name: str, confidence: float) -> str:
    """Text shown above a vehicle, for example '#T101 Car (0.98)'."""
    return f"#{format_track_id(track_id)} {class_name} ({confidence:.2f})"


def draw_vehicles(frame: np.ndarray, vehicles: list[TrackedVehicle], class_names: dict[int, str]) -> None:
    """Draw every tracked vehicle onto the frame, in place.

    `class_names` gives the settled class for each track id, which may differ
    from the detector's guess for this single frame.
    Line and text sizes scale with the frame height, so 1080p and 2K look alike.
    """
    height, width = frame.shape[:2]
    scale = height / 1080
    line = max(2, round(2 * scale))
    font_scale = 0.6 * scale
    font_line = max(1, round(1.5 * scale))
    pad = max(3, round(4 * scale))

    for vehicle in vehicles:
        x1, y1, x2, y2 = (round(value) for value in vehicle.box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), VEHICLE_BOX_COLOR, line)

        class_name = class_names.get(vehicle.track_id, vehicle.class_name)
        label = format_vehicle_label(vehicle.track_id, class_name, vehicle.confidence)
        (text_width, text_height), baseline = cv2.getTextSize(label, _FONT, font_scale, font_line)
        box_height = text_height + baseline + 2 * pad
        box_width = text_width + 2 * pad

        # Sit the label on top of the box; if that would leave the frame, put it just inside the box.
        top = y1 - box_height if y1 - box_height >= 0 else max(0, y1)
        left = min(max(x1, 0), max(0, width - box_width))
        cv2.rectangle(frame, (left, top), (left + box_width, top + box_height), LABEL_BACKGROUND, cv2.FILLED)
        cv2.putText(
            frame,
            label,
            (left + pad, top + pad + text_height),
            _FONT,
            font_scale,
            LABEL_TEXT_COLOR,
            font_line,
            cv2.LINE_AA,
        )


@dataclass
class RenderRun:
    """Result of rendering one annotated video."""

    output: Path
    frame_count: int
    decode_seconds: float
    draw_seconds: float
    encode_seconds: float


def render_annotated_video(
    info: VideoInfo,
    frames: list[list[TrackedVehicle]],
    class_names: dict[int, str],
    output: str | Path,
    progress: ProgressCallback | None = None,
) -> RenderRun:
    """Write the annotated copy of a video: same size, frame rate and frame count as the frames given.

    `frames[i]` holds the vehicles to draw on frame `i`. Audio is copied from the original.
    """
    output = Path(output)
    decode_seconds = draw_seconds = encode_seconds = 0.0
    written = 0

    audio_seconds = len(frames) / info.fps_float  # no more audio than the frames being written
    with FFmpegWriter(
        output, info.width, info.height, info.fps, audio_source=info.path, audio_seconds=audio_seconds
    ) as writer:
        source = read_frames(info.path, max_frames=len(frames))
        while True:
            started = time.perf_counter()
            frame = next(source, None)
            decode_seconds += time.perf_counter() - started
            if frame is None:
                break

            started = time.perf_counter()
            draw_vehicles(frame, frames[written], class_names)
            draw_seconds += time.perf_counter() - started

            started = time.perf_counter()
            writer.write(frame)
            encode_seconds += time.perf_counter() - started

            written += 1
            if progress is not None:
                progress(written, len(frames))

        started = time.perf_counter()
    encode_seconds += time.perf_counter() - started  # time FFmpeg takes to finish the file after the last frame

    return RenderRun(output, written, decode_seconds, draw_seconds, encode_seconds)
