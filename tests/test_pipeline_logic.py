"""Tests for the pipeline's own logic. None of them loads a model or needs the GPU."""

import csv
import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from tracko_anpr.pipeline.annotate import VEHICLE_BOX_COLOR, draw_vehicles, format_vehicle_label
from tracko_anpr.pipeline.results import (
    format_timestamp,
    frame_time,
    track_records,
    write_detections_csv,
    write_tracks_json,
)
from tracko_anpr.pipeline.tracking import (
    VEHICLE_CLASSES,
    TrackedVehicle,
    TrackingRun,
    TrackRegistry,
    format_track_id,
    lost_track_buffer,
)
from tracko_anpr.pipeline.video import (
    FFmpegWriter,
    VideoError,
    VideoInfo,
    _parse_rate,
    is_quarter_turn,
    probe_video,
    read_frames,
    stream_rotation,
)

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg is not installed"
)


def vehicle(track_id: int, class_name: str, confidence: float, box=(10.0, 20.0, 60.0, 80.0)) -> TrackedVehicle:
    return TrackedVehicle(track_id, class_name, confidence, box)


# --- tracker settings follow the frame rate -------------------------------------------------------


@pytest.mark.parametrize(("fps", "expected"), [(30, 30), (29.97, 30), (50, 50), (59.94, 60), (60, 60)])
def test_lost_track_buffer_is_one_second_at_any_frame_rate(fps, expected):
    assert lost_track_buffer(fps) == expected


def test_lost_track_buffer_scales_with_seconds_and_never_reaches_zero():
    assert lost_track_buffer(30, seconds=2.5) == 75
    assert lost_track_buffer(0.2) == 1


def test_only_the_four_agreed_vehicle_classes_exist_and_bike_is_never_used():
    assert set(VEHICLE_CLASSES.values()) == {"Car", "Motorcycle", "Bus", "Truck"}


# --- labels ----------------------------------------------------------------------------------------


def test_track_id_and_label_formats_match_the_design():
    assert format_track_id(101) == "T101"
    assert format_vehicle_label(101, "Car", 0.981) == "#T101 Car (0.98)"
    assert format_vehicle_label(102, "Motorcycle", 0.96) == "#T102 Motorcycle (0.96)"


def test_timestamps():
    assert frame_time(90, 30.0) == 3.0
    assert frame_time(60, 59.94) == pytest.approx(1.001, abs=1e-3)
    assert format_timestamp(42.9) == "00:00:42"
    assert format_timestamp(3725) == "01:02:05"


# --- one settled class per track -------------------------------------------------------------------


def test_registry_settles_a_flickering_track_on_its_best_supported_class():
    registry = TrackRegistry()
    registry.update(0, [vehicle(1, "Car", 0.9)])
    registry.update(1, [vehicle(1, "Truck", 0.5)])
    registry.update(2, [vehicle(1, "Car", 0.8)])
    track = registry.tracks[1]
    assert track.class_name == "Car"
    assert (track.first_frame, track.last_frame, track.frames_seen) == (0, 2, 3)
    assert track.best_confidence == 0.9


def test_registry_votes_by_confidence_not_by_count():
    registry = TrackRegistry()
    registry.update(0, [vehicle(7, "Car", 0.2)])
    registry.update(1, [vehicle(7, "Car", 0.2)])
    registry.update(2, [vehicle(7, "Bus", 0.9)])
    assert registry.class_names() == {7: "Bus"}


def test_registry_counts_each_track_once_and_lists_every_class():
    registry = TrackRegistry()
    registry.update(0, [vehicle(1, "Car", 0.9), vehicle(2, "Motorcycle", 0.8)])
    registry.update(1, [vehicle(1, "Car", 0.9), vehicle(3, "Car", 0.7)])
    assert registry.counts_by_class() == {"Car": 2, "Motorcycle": 1, "Bus": 0, "Truck": 0}


# --- drawing ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", [(1080, 1920), (1440, 2560)])
def test_drawing_marks_the_box_and_works_at_any_resolution(size):
    frame = np.zeros((*size, 3), dtype=np.uint8)
    draw_vehicles(frame, [vehicle(5, "Car", 0.9, (400.0, 300.0, 900.0, 700.0))], {5: "Truck"})
    assert tuple(frame[500, 400]) == VEHICLE_BOX_COLOR  # left edge of the box
    assert frame[500, 650].sum() == 0  # the middle of the vehicle is left untouched
    assert frame[:300].any()  # a label was drawn above the box


def test_drawing_copes_with_boxes_at_the_frame_edges():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    edge_boxes = [(0.0, 0.0, 50.0, 40.0), (120.0, 90.0, 159.0, 119.0), (-5.0, -5.0, 200.0, 200.0)]
    draw_vehicles(frame, [vehicle(i, "Bus", 0.5, box) for i, box in enumerate(edge_boxes)], {})
    assert frame.shape == (120, 160, 3)
    assert frame.any()


# --- video properties ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30/1", Fraction(30)),
        ("30000/1001", Fraction(30000, 1001)),
        ("0/0", None),
        ("", None),
        (None, None),
        ("x", None),
    ],
)
def test_frame_rate_parsing(text, expected):
    assert _parse_rate(text) == expected


def test_probe_rejects_missing_files_and_anything_that_is_not_mp4(tmp_path: Path):
    with pytest.raises(VideoError, match="not found"):
        probe_video(tmp_path / "absent.mp4")
    webm = tmp_path / "clip.webm"
    webm.write_bytes(b"not a real video")
    with pytest.raises(VideoError, match="Only MP4"):
        probe_video(webm)


@needs_ffmpeg
def test_probe_reports_a_clear_error_for_a_broken_mp4(tmp_path: Path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"this is not an mp4 at all")
    with pytest.raises(VideoError, match="could not read"):
        probe_video(broken)


@needs_ffmpeg
@pytest.mark.parametrize(
    ("fps", "size"), [(Fraction(30000, 1001), (64, 48)), (Fraction(60), (96, 54)), (Fraction(50), (128, 72))]
)
def test_written_video_keeps_size_frame_rate_and_frame_count(tmp_path: Path, fps, size):
    width, height = size
    output = tmp_path / "out.mp4"
    with FFmpegWriter(output, width, height, fps) as writer:
        for index in range(20):
            writer.write(np.full((height, width, 3), index * 10, dtype=np.uint8))

    assert output.is_file()
    assert not output.with_name("out.part.mp4").exists()
    info = probe_video(output)
    assert (info.width, info.height, info.fps, info.frame_count) == (width, height, fps, 20)
    assert sum(1 for _ in read_frames(output)) == 20
    assert sum(1 for _ in read_frames(output, max_frames=7)) == 7


@needs_ffmpeg
def test_a_failed_write_leaves_no_file_behind(tmp_path: Path):
    output = tmp_path / "out.mp4"
    with pytest.raises(VideoError, match="expected 64x48"), FFmpegWriter(output, 64, 48, Fraction(30)) as writer:
        writer.write(np.zeros((10, 10, 3), dtype=np.uint8))
    assert not output.exists()
    assert not output.with_name("out.part.mp4").exists()


def _source_with_audio(path: Path, video_seconds: float, audio_seconds: float) -> Path:
    """A tiny 30 FPS test video whose audio track has its own length."""
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=size=64x48:rate=30:duration={video_seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={audio_seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
    ]  # fmt: skip
    subprocess.run(command, check=True)
    return path


def _audio_seconds(path: Path) -> float:
    command = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration", "-of", "csv=p=0"]
    return float(subprocess.run([*command, str(path)], capture_output=True, text=True, check=True).stdout.strip())


@needs_ffmpeg
def test_audio_shorter_than_the_video_does_not_cut_frames_off_the_end(tmp_path: Path):
    source = _source_with_audio(tmp_path / "source.mp4", video_seconds=1.0, audio_seconds=0.5)
    output = tmp_path / "out.mp4"
    with FFmpegWriter(output, 64, 48, Fraction(30), audio_source=source, audio_seconds=1.0) as writer:
        for _ in range(30):
            writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    assert probe_video(output).frame_count == 30


@needs_ffmpeg
def test_writing_part_of_a_video_takes_only_that_much_audio(tmp_path: Path):
    source = _source_with_audio(tmp_path / "source.mp4", video_seconds=2.0, audio_seconds=2.0)
    output = tmp_path / "out.mp4"
    with FFmpegWriter(output, 64, 48, Fraction(30), audio_source=source, audio_seconds=10 / 30) as writer:
        for _ in range(10):
            writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    assert probe_video(output).frame_count == 10
    assert _audio_seconds(output) < 0.5


# --- result files ----------------------------------------------------------------------------------


def _small_run() -> tuple[VideoInfo, TrackingRun]:
    info = VideoInfo(Path("clip.mp4"), 1920, 1080, Fraction(30), 3, 0.1)
    frames = [
        [vehicle(1, "Car", 0.9)],
        [vehicle(1, "Car", 0.8), vehicle(2, "Bus", 0.7)],
        [vehicle(2, "Bus", 0.6)],
    ]
    registry = TrackRegistry()
    for index, vehicles in enumerate(frames):
        registry.update(index, vehicles)
    return info, TrackingRun(frames, registry, decode_seconds=0.1, track_seconds=0.2)


def test_detections_csv_has_one_row_per_vehicle_per_frame(tmp_path: Path):
    info, run = _small_run()
    path = write_detections_csv(tmp_path / "nested" / "detections.csv", info, run)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert [(row["frame"], row["track_id"], row["class"]) for row in rows] == [
        ("0", "1", "Car"),
        ("1", "1", "Car"),
        ("1", "2", "Bus"),
        ("2", "2", "Bus"),
    ]
    assert rows[1]["time_s"] == "0.033"
    assert (rows[0]["x1"], rows[0]["y2"]) == ("10.0", "80.0")


def test_track_summary_orders_tracks_by_first_appearance(tmp_path: Path):
    info, run = _small_run()
    records = track_records(info, run)
    assert [(r["label"], r["class"], r["first_frame"], r["last_frame"], r["frames_seen"]) for r in records] == [
        ("T1", "Car", 0, 1, 2),
        ("T2", "Bus", 1, 2, 2),
    ]

    path = write_tracks_json(tmp_path / "tracks.json", info, run, {"settings": {"image_size": 1536}})
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["video"]["fps"] == "30"
    assert document["frames_processed"] == 3
    assert document["counts"] == {"tracks": 2, "by_class": {"Car": 1, "Motorcycle": 0, "Bus": 1, "Truck": 0}}
    assert document["settings"] == {"image_size": 1536}
    assert len(document["tracks"]) == 2


# --- rotation tags on phone recordings ----------------------------------------------------------


def test_a_rotation_tag_is_read_from_side_data_or_the_old_tag():
    assert stream_rotation({"side_data_list": [{"rotation": -90}]}) == -90
    assert stream_rotation({"side_data_list": [{"displaymatrix": "..."}], "tags": {"rotate": "270"}}) == 270
    assert stream_rotation({"tags": {}}) == 0
    assert stream_rotation({}) == 0


@pytest.mark.parametrize("degrees", [90, -90, 270, -270])
def test_a_quarter_turn_swaps_width_and_height(degrees):
    assert is_quarter_turn(degrees)


@pytest.mark.parametrize("degrees", [0, 180, -180, 360])
def test_a_half_turn_or_none_keeps_the_shape(degrees):
    assert not is_quarter_turn(degrees)
