"""Command line entry point: `tracko-anpr <command>`."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from tracko_anpr.config import get_settings
from tracko_anpr.pipeline.video import VideoError, probe_video


def _progress_printer(label: str, every_seconds: float = 2.0):
    """Build a progress callback that prints at most once every few seconds, and at the end."""
    state = {"started": time.perf_counter(), "last": 0.0}

    def report(done: int, total: int) -> None:
        now = time.perf_counter()
        if done < total and now - state["last"] < every_seconds:
            return
        state["last"] = now
        elapsed = now - state["started"]
        speed = done / elapsed if elapsed > 0 else 0.0
        percent = 100 * done / total if total else 100.0
        print(f"  {label}: {done}/{total} frames ({percent:.0f}%), {speed:.1f} frames/s", flush=True)

    return report


def _peak_ram_mib() -> float:
    """Most memory this process has used, in MiB; 0 where the platform cannot say."""
    try:
        import resource
    except ImportError:
        return 0.0
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux reports kilobytes


def _run_track(args: argparse.Namespace) -> int:
    # Imported here so `tracko-anpr --help` does not load PyTorch.
    from tracko_anpr.pipeline.annotate import render_annotated_video
    from tracko_anpr.pipeline.results import write_detections_csv, write_tracks_json
    from tracko_anpr.pipeline.tracking import VehicleTracker, track_video

    settings = get_settings()
    info = probe_video(args.video)
    print(
        f"Video: {info.path.name}, {info.width}x{info.height}, {info.fps_float:.2f} FPS, "
        f"{info.frame_count} frames, {info.duration_s:.1f} s"
    )
    max_frames = None if args.max_seconds is None else max(1, round(args.max_seconds * info.fps_float))

    output_dir = args.output_dir or settings.processed_dir
    stem = info.path.stem
    video_out = output_dir / f"{stem}_annotated.mp4"
    csv_out = output_dir / f"{stem}_detections.csv"
    json_out = output_dir / f"{stem}_tracks.json"

    started = time.perf_counter()
    with VehicleTracker(
        settings.vehicle_weights,
        info.fps_float,
        settings.vehicle_image_size,
        settings.vehicle_confidence,
        settings.tracker_lost_seconds,
    ) as tracker:
        print(
            f"Detecting and tracking (YOLO26m + TrackTrack, input {tracker.image_size}, {tracker.precision}, "
            f"lost tracks kept {tracker.track_buffer} frames)"
        )
        run = track_video(info, tracker, max_frames, _progress_printer("tracking"))
        gpu_peak = tracker.gpu_memory_peak_mib()
        tracker_details = {
            "weights": settings.vehicle_weights.name,
            "image_size": tracker.image_size,
            "confidence": tracker.confidence,
            "precision": tracker.precision,
            "tracker": "tracktrack",
            "lost_seconds": settings.tracker_lost_seconds,
            "track_buffer_frames": tracker.track_buffer,
        }

    if run.frame_count == 0:
        raise VideoError(f"No frames could be read from {info.path.name}.")

    timings = {
        "tracking_decode_s": round(run.decode_seconds, 2),
        "tracking_detect_track_s": round(run.track_seconds, 2),
        "tracking_warmup_s": round(run.warmup_seconds, 2),
    }
    rendered_frames = 0
    if not args.no_video:
        print("Rendering the annotated video")
        render = render_annotated_video(
            info, run.frames, run.registry.class_names(), video_out, _progress_printer("render")
        )
        rendered_frames = render.frame_count
        timings |= {
            "render_decode_s": round(render.decode_seconds, 2),
            "render_draw_s": round(render.draw_seconds, 2),
            "render_encode_s": round(render.encode_seconds, 2),
        }
    total_seconds = time.perf_counter() - started
    timings["total_s"] = round(total_seconds, 2)
    speed = {
        "detect_track_fps": round(run.steady_fps, 1),  # after the first frame, which includes GPU start-up
        "overall_fps": round(run.frame_count / total_seconds, 1) if total_seconds else 0.0,
        "times_real_time": round(run.frame_count / info.fps_float / total_seconds, 2) if total_seconds else 0.0,
    }
    memory = {"gpu_pytorch_peak_mib": round(gpu_peak), "ram_peak_mib": round(_peak_ram_mib())}

    write_detections_csv(csv_out, info, run)
    write_tracks_json(
        json_out, info, run, {"settings": tracker_details, "timings": timings, "speed": speed, "memory": memory}
    )

    counts = run.registry.counts_by_class()
    print(f"Done in {total_seconds:.1f} s ({speed['times_real_time']}x real time)")
    print(f"  Frames: {run.frame_count} tracked, {rendered_frames} rendered")
    print(f"  Tracks: {len(run.registry.tracks)} ({', '.join(f'{name} {count}' for name, count in counts.items())})")
    print(f"  Speed: detection and tracking {speed['detect_track_fps']} frames/s, overall {speed['overall_fps']}")
    print(f"  Memory: GPU (PyTorch) {memory['gpu_pytorch_peak_mib']} MiB, RAM {memory['ram_peak_mib']} MiB")
    print(f"  Annotated video: {video_out if not args.no_video else '(not rendered)'}")
    print(f"  Detections:      {csv_out}")
    print(f"  Track summary:   {json_out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tracko-anpr", description="Vehicle ANPR proof of concept.")
    commands = parser.add_subparsers(dest="command", required=True)

    track = commands.add_parser(
        "track", help="Detect and track vehicles in an MP4 and write an annotated copy plus the detections."
    )
    track.add_argument("video", type=Path, help="Path to an MP4 video.")
    track.add_argument(
        "--output-dir", type=Path, default=None, help="Where to write results (default: storage/processed)."
    )
    track.add_argument("--max-seconds", type=float, default=None, help="Only process the first N seconds.")
    track.add_argument(
        "--no-video", action="store_true", help="Skip the annotated video; write only the detections and tracks."
    )
    track.set_defaults(handler=_run_track)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (VideoError, FileNotFoundError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
