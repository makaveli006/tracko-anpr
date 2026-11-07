"""Read a video's properties and frames, and write H.264 MP4 through FFmpeg.

Nothing here assumes a resolution or frame rate: both are read from each video.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np


class VideoError(Exception):
    """A video cannot be read or written. The message is meant to be shown to the user."""


@dataclass(frozen=True)
class VideoInfo:
    """Properties of one input video, as reported by ffprobe."""

    path: Path
    width: int
    height: int
    fps: Fraction
    frame_count: int
    duration_s: float

    @property
    def fps_float(self) -> float:
        return float(self.fps)


def _require_tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise VideoError(f"'{name}' is not installed or not on PATH. Install FFmpeg (see ARCHITECTURE.md).")
    return found


def _parse_rate(text: str | None) -> Fraction | None:
    """Turn an ffprobe rate such as '30000/1001' into a Fraction; None when it is missing or zero."""
    if not text:
        return None
    try:
        rate = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return rate if rate > 0 else None


def probe_video(path: str | Path) -> VideoInfo:
    """Read resolution, frame rate, frame count and duration from a video file."""
    path = Path(path)
    if not path.is_file():
        raise VideoError(f"Video not found: {path}")
    if path.suffix.lower() != ".mp4":
        raise VideoError(
            f"Only MP4 input is accepted, got '{path.suffix or 'no extension'}': {path.name}. "
            "Convert it to H.264 MP4 with FFmpeg first (see ARCHITECTURE.md, section 1)."
        )

    command = [
        _require_tool("ffprobe"),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames",
        "-show_entries", "stream_side_data=rotation",
        "-show_entries", "stream_tags=rotate",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]  # fmt: skip
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise VideoError(f"ffprobe could not read {path.name}: {result.stderr.strip() or 'unknown error'}")

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise VideoError(f"No video stream found in {path.name}.")
    stream = streams[0]

    fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(stream.get("r_frame_rate"))
    if fps is None:
        raise VideoError(f"Could not determine the frame rate of {path.name}.")

    duration_s = float(data.get("format", {}).get("duration") or 0.0)
    frames_text = stream.get("nb_frames")
    frame_count = int(frames_text) if frames_text and frames_text.isdigit() else round(duration_s * fps)

    width, height = int(stream["width"]), int(stream["height"])
    if is_quarter_turn(stream_rotation(stream)):
        # A phone held upright records landscape frames with a "rotate 90" tag. OpenCV applies the
        # tag and hands over upright frames, so the sizes here must be the upright ones too.
        width, height = height, width

    return VideoInfo(
        path=path,
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration_s=duration_s,
    )


def stream_rotation(stream: dict) -> int:
    """The display rotation in degrees from ffprobe's stream data (side data first, then the old tag); 0 if none."""
    for side_data in stream.get("side_data_list") or []:
        if "rotation" in side_data:
            return int(round(float(side_data["rotation"])))
    tag = (stream.get("tags") or {}).get("rotate")
    return int(round(float(tag))) if tag not in (None, "") else 0


def is_quarter_turn(rotation_degrees: int) -> bool:
    """True when the rotation swaps width and height (90 or 270 degrees either way)."""
    return rotation_degrees % 180 == 90  # Python's modulo keeps this positive, so -90 and 270 count too


def read_frames(path: str | Path, max_frames: int | None = None) -> Iterator[np.ndarray]:
    """Yield the video's frames in order, as full-resolution BGR images."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise VideoError(f"OpenCV could not open {path}.")
    try:
        count = 0
        while max_frames is None or count < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            yield frame
            count += 1
    finally:
        capture.release()


def read_selected_frames(path: str | Path, frame_numbers: set[int]) -> Iterator[tuple[int, np.ndarray]]:
    """Yield only the wanted frames, as (frame number, full-resolution BGR image), in order.

    The video is still read from the start, but frames that are not wanted are skipped
    without being converted to images, which is much faster than decoding every one.
    """
    if not frame_numbers:
        return
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise VideoError(f"OpenCV could not open {path}.")
    try:
        last = max(frame_numbers)
        index = 0
        while index <= last and capture.grab():
            if index in frame_numbers:
                ok, frame = capture.retrieve()
                if ok:
                    yield index, frame
            index += 1
    finally:
        capture.release()


class FFmpegWriter:
    """Encode BGR frames to an H.264 MP4 by piping them into FFmpeg.

    The file is written under a temporary name and renamed only when encoding
    finishes, so a half-written video never appears under the final name.
    Audio, when present, is copied from `audio_source` without re-encoding.

    Every frame written is kept, whatever the audio's length. `audio_seconds`
    limits how much audio is taken, for when only part of a video is written;
    without it the whole audio track is copied.
    """

    def __init__(
        self,
        output: str | Path,
        width: int,
        height: int,
        fps: Fraction,
        audio_source: str | Path | None = None,
        audio_seconds: float | None = None,
        crf: int = 20,
        preset: str = "fast",
    ) -> None:
        self.output = Path(output)
        self.width = width
        self.height = height
        self._partial = self.output.with_name(f"{self.output.stem}.part.mp4")
        self.output.parent.mkdir(parents=True, exist_ok=True)

        keyframe_interval = max(1, round(fps * 2))  # a keyframe every 2 seconds keeps seeking accurate
        command = [
            _require_tool("ffmpeg"),
            "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "-",
        ]  # fmt: skip
        if audio_source is not None:
            if audio_seconds is not None:
                command += ["-t", f"{audio_seconds:.6f}"]  # applies to the audio input that follows
            command += ["-i", str(audio_source)]
        command += ["-map", "0:v:0"]
        if audio_source is not None:
            command += ["-map", "1:a:0?"]
        command += [
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-g", str(keyframe_interval),
        ]  # fmt: skip
        if audio_source is not None:
            # No `-shortest`: an audio track a few milliseconds shorter than the video would cut frames off the end.
            command += ["-c:a", "copy"]
        command += ["-movflags", "+faststart", str(self._partial)]

        # FFmpeg's messages go to a file, not a pipe: an unread pipe could fill up and stall the encode.
        # The file stays open for as long as FFmpeg runs and is closed in close().
        self._log = tempfile.TemporaryFile()  # noqa: SIM115
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._log)

    def write(self, frame: np.ndarray) -> None:
        if frame.shape[0] != self.height or frame.shape[1] != self.width:
            raise VideoError(f"Frame is {frame.shape[1]}x{frame.shape[0]}, expected {self.width}x{self.height}.")
        assert self._process.stdin is not None
        try:
            self._process.stdin.write(frame.tobytes())
        except BrokenPipeError:
            raise VideoError(f"FFmpeg stopped while encoding: {self._read_log()}") from None

    def close(self, keep: bool = True) -> None:
        """Finish encoding. With `keep=False` the partial file is discarded."""
        if self._process.stdin is not None and not self._process.stdin.closed:
            self._process.stdin.close()
        return_code = self._process.wait()
        message = self._read_log()
        self._log.close()

        if not keep or return_code != 0:
            self._partial.unlink(missing_ok=True)
            if return_code != 0:
                raise VideoError(f"FFmpeg failed to write {self.output.name}: {message or 'unknown error'}")
            return
        self._partial.replace(self.output)

    def _read_log(self) -> str:
        self._log.seek(0)
        return self._log.read().decode(errors="replace").strip()

    def __enter__(self) -> FFmpegWriter:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close(keep=exc_type is None)
