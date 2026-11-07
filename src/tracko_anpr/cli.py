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


def _run_track(args: argparse.Namespace) -> int:
    # Imported here so `tracko-anpr --help` does not load PyTorch.
    from tracko_anpr.pipeline.annotate import render_annotated_video
    from tracko_anpr.pipeline.results import write_detections_csv, write_tracks_json
    from tracko_anpr.pipeline.runner import memory_peaks
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
    memory = memory_peaks()

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


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _run_read_plates(args: argparse.Namespace) -> int:
    from tracko_anpr.pipeline.ocr_client import OcrClient

    if not args.folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {args.folder}")
    images = sorted(p for p in args.folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise FileNotFoundError(f"No images in {args.folder}")

    settings = get_settings()
    started = time.perf_counter()
    with OcrClient.for_project(
        settings.ocr_project,
        start_timeout=settings.ocr_start_timeout_seconds,
        request_timeout=settings.ocr_request_timeout_seconds,
    ) as reader:
        ready = time.perf_counter()
        readings = reader.read(images)
        finished = time.perf_counter()
        device = reader.device

    width = max(len(image.name) for image in images)
    for image, reading in zip(images, readings, strict=True):
        shown = "(unreadable)" if reading.unreadable else (reading.text or "(nothing read)")
        print(f"{image.name:<{width}}  {shown:<16}  {reading.confidence:.4f}")
    print(
        f"\n{len(images)} plates through the reader service on {device}: started in {ready - started:.1f} s, "
        f"read in {finished - ready:.2f} s ({1000 * (finished - ready) / len(images):.1f} ms per plate)"
    )
    return 0


STAGE_TITLES = {
    "video_uploaded": "Video uploaded",
    "vehicle_detection": "Vehicle detection (YOLO26m)",
    "vehicle_tracking": "Vehicle tracking (TrackTrack)",
    "plate_detection": "Plate detection (YOLO26s)",
    "ocr": "OCR (Awiros-ANPR-OCR)",
    "validation": "Multi-frame validation",
    "result_generation": "Result generation",
}


def _stage_printer(every_seconds: float = 3.0):
    """Build a stage-progress callback that prints each stage's start, occasional progress, and completion."""
    state = {"stage": None, "last": 0.0, "started": 0.0, "finished": set()}

    def report(stage: str, done: int, total: int) -> None:
        if stage == "vehicle_tracking" or stage in state["finished"]:
            return  # tracking runs in the same pass as detection; one line of progress covers both
        now = time.perf_counter()
        title = STAGE_TITLES[stage]
        if stage == "vehicle_detection":
            title = "Vehicle detection and tracking (YOLO26m + TrackTrack)"
        if stage != state["stage"]:
            state.update(stage=stage, last=0.0, started=now)
        finished = done >= total
        if not finished and now - state["last"] < every_seconds:
            return
        state["last"] = now
        if finished:
            state["finished"].add(stage)
            print(f"  [done] {title}: {total} in {now - state['started']:.1f} s", flush=True)
        else:
            print(f"         {title}: {done}/{total} ({100 * done / total:.0f}%)", flush=True)

    return report


def _open_database(settings):
    """An engine for the project database, or a clear error when it is down or not migrated."""
    from tracko_anpr.db.session import DatabaseUnavailable, check_connection, current_revision, make_engine

    engine = make_engine(settings.database_url)
    check_connection(engine)
    if current_revision(engine) is None:
        raise DatabaseUnavailable("The database has no tables yet. Run: uv run alembic upgrade head")
    return engine


def _run_process(args: argparse.Namespace) -> int:
    # Imported here so `tracko-anpr --help` does not load PyTorch.
    from tracko_anpr.pipeline.runner import PipelineOptions, run_pipeline
    from tracko_anpr.pipeline.validation import CONFIRMED

    settings = get_settings()
    info = probe_video(args.video)
    print(
        f"Video: {info.path.name}, {info.width}x{info.height}, {info.fps_float:.2f} FPS, "
        f"{info.frame_count} frames, {info.duration_s:.1f} s"
    )
    options = PipelineOptions(render_video=not args.no_video, max_seconds=args.max_seconds)

    job_id = video_name = None
    if not args.no_db:
        # Checked before the run, so a database problem shows up now and not after ten minutes of work.
        from tracko_anpr.db.models import COMMAND_LINE, PROCESSING, ProcessingJob
        from tracko_anpr.db.session import make_session_factory, session_scope
        from tracko_anpr.db.store import create_job, mark_failed, register_video, store_result

        factory = make_session_factory(_open_database(settings))
        with session_scope(factory) as session:
            video = register_video(session, info, settings.root, COMMAND_LINE, name=args.name)
            job = create_job(session, video, PROCESSING)
            job_id, video_name = job.id, video.name
        print(f"Database: video {video.id} ({video_name}), job {job_id}")

    try:
        result = run_pipeline(args.video, settings, options, _stage_printer(), name=video_name or args.name)
    except Exception as error:
        if job_id is not None:
            with session_scope(factory) as session:
                mark_failed(session, session.get(ProcessingJob, job_id), f"{type(error).__name__}: {error}")
        raise

    if job_id is not None:
        with session_scope(factory) as session:
            store_result(session, session.get(ProcessingJob, job_id), result, settings.root)

    summary, timings = result.summary, result.timings
    coverage = summary["recognition_coverage"]
    print(f"\nFinished in {timings['total_s']:.1f} s")
    print(
        f"  Tracks: {summary['unique_tracks']} in all; {summary['total_vehicles']} count as vehicles "
        f"({summary['tracks_too_brief_or_small']} too brief or too far, {summary['camera_car_tracks']} the camera car, "
        f"{summary['repeat_tracks']} the same vehicle seen again)"
    )
    print(f"  Vehicles by type: {', '.join(f'{name} {count}' for name, count in summary['by_class'].items())}")
    print(
        f"  Plates: {summary['confirmed']} confirmed, {summary['unconfirmed']} unconfirmed, "
        f"{summary['not_detected']} not detected"
    )
    if coverage is not None:
        print(
            f"  Recognition coverage: {100 * coverage:.1f}% "
            f"({summary['confirmed']} of {summary['total_vehicles']} vehicles; coverage, not accuracy)"
        )
    confirmed = [vehicle for vehicle in result.vehicles if vehicle.status == CONFIRMED]
    if confirmed:
        print("  Confirmed numbers:")
        for vehicle in confirmed:
            decision = vehicle.decision
            repeat = f"  (same vehicle as T{vehicle.same_vehicle_as})" if vehicle.same_vehicle_as is not None else ""
            print(
                f"    T{vehicle.track_id:<5} {vehicle.class_name:<11} {decision.text:<11} "
                f"{decision.confidence:.2f}  {decision.support} of {decision.readings} readings{repeat}"
            )
    print("  Files:")
    for label, path in result.files.items():
        print(f"    {label:<16} {path}")
    if job_id is not None:
        print(f"  Database: stored as job {job_id} of video {video_name}")
    return 0


def _run_db_status(args: argparse.Namespace) -> int:
    """Is the database reachable and migrated, and what is in it?"""
    from sqlalchemy import func, select

    from tracko_anpr.db import metrics
    from tracko_anpr.db.models import (
        AppSetting,
        DemoRegistryEntry,
        PlateObservation,
        ProcessingJob,
        RecognitionEvent,
        VehicleTrack,
        Video,
    )
    from tracko_anpr.db.session import current_revision, make_session_factory, session_scope

    settings = get_settings()
    engine = _open_database(settings)
    print(f"Database: {engine.url.render_as_string(hide_password=True)}")
    print(f"Migration: {current_revision(engine)}")
    tables = [Video, ProcessingJob, VehicleTrack, PlateObservation, RecognitionEvent, DemoRegistryEntry, AppSetting]
    with session_scope(make_session_factory(engine)) as session:
        print("Rows:")
        for table in tables:
            count = session.scalar(select(func.count()).select_from(table))
            print(f"  {table.__tablename__:<20} {count}")
        overall = metrics.summary(session)
        print("Across all videos (latest completed job of each):")
        print(f"  Videos processed     {overall.videos_processed}")
        print(f"  Unique tracks        {overall.unique_tracks}")
        print(f"  Total vehicles       {overall.total_vehicles}")
        print(f"  Confirmed plates     {overall.confirmed_plates}")
        coverage = "n/a" if overall.recognition_coverage is None else f"{100 * overall.recognition_coverage:.1f}%"
        print(f"  Recognition coverage {coverage} (coverage, not accuracy)")
        if overall.average_processing_seconds is not None:
            print(f"  Avg. processing time {overall.average_processing_seconds:.0f} s per video")
        if overall.last_run_at is not None:
            print(f"  Last run             {overall.last_run_at:%Y-%m-%d %H:%M:%S %Z}")
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

    read_plates = commands.add_parser(
        "read-plates", help="Read plate crops in a folder by starting the plate reader service and asking it."
    )
    read_plates.add_argument("folder", type=Path, help="A folder of plate images.")
    read_plates.set_defaults(handler=_run_read_plates)

    process = commands.add_parser(
        "process",
        help="Run the whole pipeline on an MP4: detect, track, find and read plates, validate, write the results.",
    )
    process.add_argument("video", type=Path, help="Path to an MP4 video.")
    process.add_argument("--max-seconds", type=float, default=None, help="Only process the first N seconds.")
    process.add_argument("--no-video", action="store_true", help="Skip the annotated video; write only the results.")
    process.add_argument("--name", default=None, help="Name for this run's result folders (default: the file name).")
    process.add_argument(
        "--no-db", action="store_true", help="Do not record the video and its results in the database; files only."
    )
    process.set_defaults(handler=_run_process)

    db_status = commands.add_parser(
        "db-status", help="Check the database connection and migration, and show what is stored."
    )
    db_status.set_defaults(handler=_run_db_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    from tracko_anpr.db.session import DatabaseUnavailable
    from tracko_anpr.pipeline.ocr_client import OcrError

    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (VideoError, FileNotFoundError, OcrError, DatabaseUnavailable) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
