"""Command line entry point: `tracko-anpr <command>`."""

from __future__ import annotations

import argparse
import json
import os
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


def _run_check(args: argparse.Namespace) -> int:
    """Measure the plate sizes of a video from a few sampled frames, without processing it."""
    from tracko_anpr.pipeline.plate_check import check_plate_sizes

    settings = get_settings()
    info = probe_video(args.video)
    print(
        f"Video: {info.path.name}, {info.width}x{info.height}, {info.fps_float:.2f} FPS, "
        f"{info.frame_count} frames, {info.duration_s:.1f} s"
    )
    started = time.perf_counter()
    found = check_plate_sizes(info, settings, count=args.frames)
    print(f"Checked {found.frames_sampled} frames in {time.perf_counter() - started:.1f} s")
    print(f"  Vehicles seen      {found.vehicles_seen}")
    print(f"  Plates seen        {found.plates_seen}")
    if found.plates_seen:
        print(f"  Median plate width {found.median_width_px} px")
        print(f"  Largest (p90)      {found.largest_width_px} px")
        print(f"  Under 60 px        {found.share_under_60:.0%}   130 px and over {found.share_over_130:.0%}")
    print(f"  Verdict            {found.verdict}")
    print(f"  {found.message}")
    print("  Size only: blur, angle and light are not checked.")
    if args.json:
        args.json.write_text(json.dumps(found.as_dict(), indent=2), encoding="utf-8")
        print(f"  Written to {args.json}")
    return 0


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


def _timestamp() -> str:
    return time.strftime("%H:%M:%S")


def _log(message: str) -> None:
    print(f"[{_timestamp()}] {message}", flush=True)


def _run_worker(args: argparse.Namespace) -> int:
    import signal

    from tracko_anpr.db.session import make_session_factory
    from tracko_anpr.worker.service import Worker

    settings = get_settings()
    worker = Worker(
        settings,
        make_session_factory(_open_database(settings)),
        poll_seconds=args.poll_seconds,
        log=_log,
    )

    def ask_to_stop(signum, frame):
        # Runs inside a signal handler: no print() here (not re-entrant; `pkill` can deliver two SIGTERMs,
        # one through uv and one directly, the second while the first is still being handled).
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # a repeat is not a second request
        signal.signal(signal.SIGINT, signal.default_int_handler)  # a second Ctrl+C raises KeyboardInterrupt
        worker.request_stop()
        message = f"[{_timestamp()}] stop requested; finishing the current job first (Ctrl+C again interrupts it)\n"
        os.write(sys.stdout.fileno(), message.encode())

    signal.signal(signal.SIGINT, ask_to_stop)
    signal.signal(signal.SIGTERM, ask_to_stop)
    worker.start()
    try:
        ran = worker.run_forever(once=args.once)
    except KeyboardInterrupt:
        _log("interrupted; the job is back in the queue")
        return 130
    _log(f"stopped after {ran} job(s)")
    return 0


def _run_ingest(args: argparse.Namespace) -> int:
    """Register a video that is already on disk, without copying it."""
    from tracko_anpr.db.models import INGESTED
    from tracko_anpr.db.session import make_session_factory, session_scope
    from tracko_anpr.db.store import register_video

    settings = get_settings()
    info = probe_video(args.video)
    with session_scope(make_session_factory(_open_database(settings))) as session:
        video = register_video(session, info, settings.root, INGESTED, name=args.name)
        print(
            f"Video {video.id}: {video.name} ({video.width}x{video.height}, {video.fps_decimal:.2f} FPS, "
            f"{video.duration_s:.1f} s) at {video.file_path}"
        )
    return 0


def _run_enqueue(args: argparse.Namespace) -> int:
    """Queue a video for the worker: by id, by name, or by path (registered first if new)."""
    from tracko_anpr.db.models import INGESTED
    from tracko_anpr.db.session import make_session_factory, session_scope
    from tracko_anpr.db.store import find_video, queue_job, register_video

    settings = get_settings()
    with session_scope(make_session_factory(_open_database(settings))) as session:
        video = find_video(session, args.video)
        if video is None:
            path = Path(args.video)
            if not path.is_file():
                raise FileNotFoundError(f"No video with id or name '{args.video}', and no such file.")
            video = register_video(session, probe_video(path), settings.root, INGESTED, name=args.name)
        job, created = queue_job(session, video)
        if created:
            print(f"Queued job {job.id} for video {video.id} ({video.name}). Start a worker: uv run tracko-anpr worker")
        else:
            print(f"Video {video.id} ({video.name}) already has job {job.id} ({job.status}); nothing added.")
    return 0


def _run_jobs(args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from tracko_anpr.db.models import ProcessingJob
    from tracko_anpr.db.session import make_session_factory, session_scope

    settings = get_settings()
    with session_scope(make_session_factory(_open_database(settings))) as session:
        jobs = session.scalars(select(ProcessingJob).order_by(ProcessingJob.id.desc()).limit(args.limit)).all()
        if not jobs:
            print("No jobs.")
            return 0
        print(f"{'job':>4}  {'video':<24} {'status':<11} {'stage':<20} {'progress':>9}  {'time':>7}  {'att':>3}  error")
        for job in reversed(jobs):
            progress = f"{100 * job.stage_done / job.stage_total:.0f}%" if job.stage_total else ""
            seconds = job.processing_seconds
            if seconds is None and job.started_at and job.finished_at:
                seconds = (job.finished_at - job.started_at).total_seconds()
            print(
                f"{job.id:>4}  {job.video.name[:24]:<24} {job.status:<11} {job.stage or '':<20} {progress:>9}  "
                f"{f'{seconds:.0f} s' if seconds is not None else '':>7}  {job.attempts:>3}  {(job.error or '')[:60]}"
            )
    return 0


def _run_web(args: argparse.Namespace) -> int:
    """The web app: FastAPI with the NiceGUI dashboard mounted, in one process."""
    import uvicorn

    from tracko_anpr.api.app import create_app

    settings = get_settings()
    _open_database(settings)  # fail now, with a clear message, rather than on the first request
    host = args.host or settings.web_host
    port = args.port or settings.web_port
    _log(f"web app on http://{host}:{port}/ (API docs at /api/docs); press Ctrl+C to stop")
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
    return 0


def _run_reset_data(args: argparse.Namespace) -> int:
    """Delete every video, job, detection and registry record, and every file under storage/."""
    import shutil

    from sqlalchemy import delete, func, select

    from tracko_anpr.db.models import AppSetting, DemoRegistryEntry, ProcessingJob, Video
    from tracko_anpr.db.session import make_session_factory, session_scope

    settings = get_settings()
    if not args.yes:
        print("This deletes all processed results, uploads, crops and the demo registry. Run again with --yes.")
        return 1
    with session_scope(make_session_factory(_open_database(settings))) as session:
        videos = session.scalar(select(func.count()).select_from(Video))
        jobs = session.scalar(select(func.count()).select_from(ProcessingJob))
        session.execute(delete(Video))  # jobs, tracks, observations and events go with it (ON DELETE CASCADE)
        session.execute(delete(DemoRegistryEntry))
        session.execute(delete(AppSetting))
    removed = 0
    for folder in (settings.uploads_dir, settings.processed_dir, settings.vehicle_crops_dir, settings.plate_crops_dir):
        for item in folder.iterdir() if folder.is_dir() else []:
            if item.name == ".gitkeep":
                continue
            shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)
            removed += 1
    print(
        f"Deleted {videos} videos and {jobs} jobs with their results, the demo registry, "
        f"and {removed} items under storage/."
    )
    return 0


def _run_seed_registry(args: argparse.Namespace) -> int:
    """Fill the FICTIONAL demonstration registry from the plates recognized so far."""
    from tracko_anpr.db.session import make_session_factory, session_scope
    from tracko_anpr.services import registry, registry_seed

    settings = get_settings()
    with session_scope(make_session_factory(_open_database(settings))) as session:
        outcome = registry_seed.seed(
            session, share=args.share, extra=args.extra, seed_value=args.seed, reset=args.reset, near=args.near
        )
        total = registry.count(session)
    print(
        f"Confirmed numbers in the processed videos: {outcome.confirmed_numbers}. "
        f"Created {outcome.created_from_videos} fictional records for them (about {args.share:.0%}), "
        f"{outcome.created_extra} for numbers seen in no video, {outcome.created_near} near-miss records one "
        f"character from a number without a record (about {args.near:.0%}); {outcome.skipped_existing} already "
        f"existed. "
        f"Registry now holds {total} fictional records."
    )
    print("Demonstration data only: every record is invented; no real registration database is consulted.")
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

    check = commands.add_parser(
        "check", help="Measure the plate sizes in an MP4 from a few sampled frames: will its plates be readable?"
    )
    check.add_argument("video", type=Path, help="Path to an MP4 video.")
    check.add_argument("--frames", type=int, default=24, help="How many frames to sample (default 24).")
    check.add_argument("--json", type=Path, default=None, help="Also write the figures to this JSON file.")
    check.set_defaults(handler=_run_check)

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

    worker = commands.add_parser("worker", help="Run queued jobs from the database, one at a time, until stopped.")
    worker.add_argument("--once", action="store_true", help="Run at most one job, then exit.")
    worker.add_argument("--poll-seconds", type=float, default=2.0, help="How often to look for work (default 2).")
    worker.set_defaults(handler=_run_worker)

    ingest = commands.add_parser("ingest", help="Register a video already on disk, without copying it.")
    ingest.add_argument("video", type=Path, help="Path to an MP4 video.")
    ingest.add_argument("--name", default=None, help="Name for the video (default: the file name).")
    ingest.set_defaults(handler=_run_ingest)

    enqueue = commands.add_parser("enqueue", help="Queue a video for the worker.")
    enqueue.add_argument("video", help="A video id, a video name, or the path of an MP4 (registered if new).")
    enqueue.add_argument("--name", default=None, help="Name for a newly registered video.")
    enqueue.set_defaults(handler=_run_enqueue)

    jobs = commands.add_parser("jobs", help="List processing jobs, newest last.")
    jobs.add_argument("--limit", type=int, default=20)
    jobs.set_defaults(handler=_run_jobs)

    reset = commands.add_parser("reset-data", help="Delete all results, uploads, crops and the demo registry.")
    reset.add_argument("--yes", action="store_true", help="Really do it.")
    reset.set_defaults(handler=_run_reset_data)

    seed = commands.add_parser(
        "seed-registry", help="Generate the FICTIONAL demo registry from a share of the recognized plates."
    )
    seed.add_argument("--share", type=float, default=0.5, help="Share of confirmed numbers to give a record (0.5).")
    seed.add_argument("--extra", type=int, default=4, help="Fictional numbers seen in no video to add (4).")
    seed.add_argument("--seed", type=int, default=2026, help="Random seed, so a re-run adds nothing new.")
    seed.add_argument(
        "--near",
        type=float,
        default=0.25,
        help="Share of the numbers left without a record to give a near-miss (0.25).",
    )
    seed.add_argument("--reset", action="store_true", help="Delete the existing registry first.")
    seed.set_defaults(handler=_run_seed_registry)

    web = commands.add_parser("web", help="Serve the API and the dashboard in one process.")
    web.add_argument("--host", default=None, help="Listen address (default TRACKO_WEB_HOST or 0.0.0.0).")
    web.add_argument("--port", type=int, default=None, help="Port (default TRACKO_WEB_PORT or 8080).")
    web.set_defaults(handler=_run_web)
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
