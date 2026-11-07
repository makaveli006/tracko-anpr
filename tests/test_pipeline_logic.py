"""Tests for the pipeline's own logic. None of them loads a model or needs the GPU."""

import csv
import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from tracko_anpr.pipeline.annotate import (
    VEHICLE_BOX_COLOR,
    PlateLabel,
    draw_vehicles,
    format_vehicle_label,
    output_size,
    plate_boxes_by_frame,
    render_annotated_video,
)
from tracko_anpr.pipeline.direction import Direction, DirectionRules, direction_label, short_direction, travel_direction
from tracko_anpr.pipeline.plate_check import (
    BORDERLINE,
    GOOD,
    LOW,
    NO_PLATES,
    NO_VEHICLES,
    sample_frame_numbers,
    summarise,
)
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
    read_frames_at,
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


# --- the plate-size check -----------------------------------------------------------------------------


def test_sampled_frames_are_spread_over_the_video_and_skip_its_ends():
    numbers = sample_frame_numbers(1000, 16)
    assert len(numbers) == 16 and numbers == sorted(numbers)
    assert numbers[0] == 50 and numbers[-1] == 949  # the first and last 5% are left out
    short = sample_frame_numbers(20, 16)
    assert len(short) == 16 and short[0] == 1 and short[-1] == 18
    assert sample_frame_numbers(12, 16) == list(range(0, 11))  # shorter still: every frame that fits
    assert sample_frame_numbers(3, 16) == [0, 1]
    assert sample_frame_numbers(0, 16) == [] and sample_frame_numbers(100, 0) == []


def test_the_verdict_follows_the_largest_plates_seen():
    good = summarise([40, 55, 70, 90, 120, 135, 150, 160, 170, 180], vehicles_seen=12, frames_sampled=16)
    assert (good.verdict, good.plates_seen, good.vehicles_seen) == (GOOD, 10, 12)
    assert good.largest_width_px == 170 and good.median_width_px == 128  # the 90th percentile, the median
    assert (good.share_under_60, good.share_over_130) == (0.2, 0.5)
    assert "170 px" in good.message and "most of them should be read" in good.message

    assert summarise([40, 50, 60, 70, 80, 90, 100, 110, 120, 125], 10, 16).verdict == BORDERLINE
    low = summarise([20, 30, 35, 40, 45, 50, 55], 7, 16)
    assert low.verdict == LOW and "Move closer or zoom in" in low.message
    assert summarise([], 5, 16).verdict == NO_PLATES
    none = summarise([], 0, 16)
    assert none.verdict == NO_VEHICLES and none.median_width_px is None and "16 sampled frames" in none.message
    assert set(good.as_dict()) >= {"verdict", "message", "largest_width_px"}


@needs_ffmpeg
def test_frames_can_be_read_by_seeking_to_their_numbers(tmp_path: Path):
    info = _test_video(tmp_path / "source.mp4", 64, 48, 12)
    got = list(read_frames_at(info.path, [9, 2, 7, 40, -1]))
    assert [number for number, _ in got] == [2, 7, 9]  # ascending, out-of-range numbers ignored
    assert all(frame.shape == (48, 64, 3) for _, frame in got)
    assert list(read_frames_at(info.path, [])) == []


# --- travel direction from the boxes ----------------------------------------------------------------


def _track(count: int, height_from: float, height_to: float, x_from: float, x_to: float):
    """Boxes whose height and x-centre change evenly from the first frame to the last."""
    boxes = []
    for i in range(count):
        t = i / max(count - 1, 1)
        height = height_from + (height_to - height_from) * t
        centre = x_from + (x_to - x_from) * t
        boxes.append((i, (centre - 40.0, 500.0 - height, centre + 40.0, 500.0)))
    return boxes


def test_a_vehicle_that_grows_comes_towards_the_camera_and_one_that_shrinks_goes_away():
    assert travel_direction(_track(30, 60, 200, 960, 960), 1920) == Direction("towards", None)
    assert travel_direction(_track(30, 200, 60, 960, 960), 1920) == Direction("away", None)
    assert travel_direction(_track(30, 100, 110, 960, 960), 1920) == Direction(None, None)  # 10%: not enough


def test_sideways_travel_is_left_or_right_as_a_share_of_the_frame_width():
    assert travel_direction(_track(30, 100, 100, 200, 800), 1920) == Direction(None, "right")
    assert travel_direction(_track(30, 100, 100, 800, 200), 1920) == Direction(None, "left")
    assert travel_direction(_track(30, 100, 100, 900, 1000), 1920) == Direction(None, None)  # 5% of the width
    assert travel_direction(_track(30, 60, 200, 1500, 400), 1920) == Direction("towards", "left")


def test_direction_uses_medians_so_one_bad_first_box_does_not_decide():
    boxes = _track(40, 100, 100, 960, 960)
    boxes[0] = (0, (900.0, 0.0, 1020.0, 500.0))  # a 500 px tall box in the first frame only
    assert travel_direction(boxes, 1920) == Direction(None, None)
    assert travel_direction(boxes[:1], 1920) == Direction(None, None)  # one box: nothing to compare
    assert travel_direction([], 1920) == Direction(None, None)
    strict = DirectionRules(approach_ratio=1.05)
    assert travel_direction(_track(30, 100, 110, 960, 960), 1920, strict) == Direction("towards", None)


def test_direction_words():
    assert direction_label("towards", None) == "Towards camera"
    assert direction_label("away", "left") == "Away from camera, left"
    assert direction_label(None, "right") == "Right"
    assert direction_label(None, None) == "Undetermined"
    assert Direction("towards", "right").label == "Towards camera, right"
    assert short_direction("away", None) == "Away" and short_direction(None, None) == "—"


# --- plate outlines without the detector, and the scaled-down annotated copy ----------------------


def _moving_track(track_id: int, count: int, start=(100.0, 100.0, 300.0, 200.0), step=10.0):
    """One vehicle whose box moves `step` pixels right each frame."""
    x1, y1, x2, y2 = start
    return [[vehicle(track_id, "Car", 0.9, (x1 + i * step, y1, x2 + i * step, y2))] for i in range(count)]


def test_plate_boxes_follow_the_vehicle_between_the_sighted_frames():
    frames = _moving_track(7, 5)
    # Sighted in frames 0 and 4; the plate is lower on the vehicle in frame 4 than in frame 0.
    sightings = {7: [(4, (240.0, 180.0, 280.0, 196.0)), (0, (150.0, 160.0, 190.0, 176.0))]}
    located = plate_boxes_by_frame(frames, sightings)

    assert sorted(located) == [0, 1, 2, 3, 4]
    assert located[0][7] == pytest.approx((150.0, 160.0, 190.0, 176.0))
    assert located[4][7] == pytest.approx((240.0, 180.0, 280.0, 196.0))
    # Frame 2: the vehicle box is (120, 100, 320, 200); the fractions are the midpoint of the two sightings.
    assert located[2][7] == pytest.approx((195.0, 170.0, 235.0, 186.0))


def test_plate_boxes_are_held_outside_the_sighted_span_and_skip_small_vehicles():
    frames = _moving_track(3, 6)
    frames[5] = [vehicle(3, "Car", 0.9, (500.0, 100.0, 540.0, 120.0))]  # far away: 20 px tall
    sightings = {3: [(2, (160.0, 150.0, 200.0, 170.0)), (3, (170.0, 150.0, 210.0, 170.0))]}
    located = plate_boxes_by_frame(frames, sightings, min_height=50)

    # Before the first sighting the fractions of frame 2 are used on frame 0's box (shifted by 20 px).
    assert located[0][3] == pytest.approx((140.0, 150.0, 180.0, 170.0))
    # After the last sighting the fractions of frame 3 are used on frame 4's box.
    assert located[4][3] == pytest.approx((180.0, 150.0, 220.0, 170.0))
    assert 5 not in located  # too small to outline
    assert plate_boxes_by_frame(frames, {}) == {}
    assert plate_boxes_by_frame(frames, {9: [(0, (0.0, 0.0, 1.0, 1.0))]}) == {}  # never tracked


def test_output_size_scales_only_inputs_taller_than_the_limit():
    assert output_size(3840, 2160, 1080) == (1920, 1080, 0.5)
    assert output_size(2560, 1440, 1080) == (1920, 1080, 0.75)
    assert output_size(1920, 1080, 1080) == (1920, 1080, 1.0)
    assert output_size(1280, 720, 1080) == (1280, 720, 1.0)
    assert output_size(3840, 2160, None) == (3840, 2160, 1.0)
    assert output_size(1000, 1000, 333)[0] % 2 == 0


def _test_video(path: Path, width: int, height: int, frames: int, fps: int = 30) -> VideoInfo:
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=black:size={width}x{height}:rate={fps}",
        "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ]  # fmt: skip
    subprocess.run(command, check=True)
    return probe_video(path)


def _greenish(pixel) -> bool:
    blue, green, red = (int(value) for value in pixel)
    return green > 120 and green > red + 40 and green > blue + 40


@needs_ffmpeg
def test_rendered_copy_is_scaled_down_to_max_height_with_its_boxes(tmp_path: Path):
    info = _test_video(tmp_path / "source.mp4", 128, 96, 10)
    frames = [[vehicle(1, "Car", 0.9, (32.0, 32.0, 112.0, 88.0))] for _ in range(10)]
    plate_boxes = {index: {1: (60.0, 70.0, 90.0, 80.0)} for index in range(10)}
    labels = {1: PlateLabel("KL07AB1234", 0.95, True)}
    output = tmp_path / "annotated.mp4"

    render = render_annotated_video(
        info, frames, {1: "Car"}, output, plate_labels=labels, plate_boxes=plate_boxes, max_height=48
    )

    assert (render.width, render.height, render.frame_count) == (64, 48, 10)
    written = probe_video(output)
    assert (written.width, written.height, written.frame_count, written.fps) == (64, 48, 10, info.fps)
    first = next(read_frames(output))
    assert _greenish(first[40, 16])  # the vehicle's left edge, at half scale (x 32 -> 16, y 32..88 -> 16..44)
    assert not _greenish(first[40, 8])  # nothing drawn outside the box


@needs_ffmpeg
def test_rendered_copy_keeps_the_input_size_when_it_is_not_taller_than_the_limit(tmp_path: Path):
    info = _test_video(tmp_path / "source.mp4", 128, 96, 5)
    frames = [[vehicle(1, "Car", 0.9, (32.0, 32.0, 112.0, 88.0))] for _ in range(5)]
    output = tmp_path / "annotated.mp4"
    render = render_annotated_video(info, frames, {1: "Car"}, output, max_height=1080)
    assert (render.width, render.height, render.frame_count) == (128, 96, 5)
    written = probe_video(output)
    assert (written.width, written.height, written.frame_count) == (128, 96, 5)
    assert _greenish(next(read_frames(output))[60, 32])


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
