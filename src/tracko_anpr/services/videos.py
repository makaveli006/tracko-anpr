"""Videos: uploading, registering files already on disk, and listing what is known."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracko_anpr.config import Settings
from tracko_anpr.db.metrics import latest_completed_jobs
from tracko_anpr.db.models import INGESTED, UPLOADED, ProcessingJob, Video
from tracko_anpr.db.store import register_video
from tracko_anpr.pipeline.runner import relative_path
from tracko_anpr.pipeline.video import VideoError, probe_video

MAX_UPLOAD_BYTES = 8 * 1024**3  # 8 GB: larger files are registered with `ingest` instead


class InvalidVideo(ValueError):
    """The uploaded file is not an MP4 video we can process. The message is for the user."""


@dataclass(frozen=True)
class JobBrief:
    id: int
    status: str
    stage: str | None
    progress: float
    """0 to 1 within the current stage."""
    created_at: datetime
    finished_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class VideoSummary:
    id: int
    name: str
    original_filename: str
    source: str
    size_bytes: int | None
    width: int
    height: int
    fps: str
    fps_decimal: float
    frame_count: int
    duration_s: float
    created_at: datetime
    latest_job: JobBrief | None
    """The newest job of any status: what the Upload page shows."""
    completed_job_id: int | None
    """The job whose results the dashboard shows (the latest completed one), if any."""


def _brief(job: ProcessingJob | None) -> JobBrief | None:
    if job is None:
        return None
    progress = job.stage_done / job.stage_total if job.stage_total else 0.0
    return JobBrief(job.id, job.status, job.stage, round(progress, 4), job.created_at, job.finished_at, job.error)


def summarize_video(session: Session, video: Video) -> VideoSummary:
    latest = session.scalar(
        select(ProcessingJob).where(ProcessingJob.video_id == video.id).order_by(ProcessingJob.id.desc()).limit(1)
    )
    completed = session.scalar(latest_completed_jobs(video.id))
    return VideoSummary(
        id=video.id,
        name=video.name,
        original_filename=video.original_filename,
        source=video.source,
        size_bytes=video.size_bytes,
        width=video.width,
        height=video.height,
        fps=video.fps,
        fps_decimal=video.fps_decimal,
        frame_count=video.frame_count,
        duration_s=video.duration_s,
        created_at=video.created_at,
        latest_job=_brief(latest),
        completed_job_id=completed,
    )


def list_videos(session: Session) -> list[VideoSummary]:
    """Every registered video, newest first."""
    videos = session.scalars(select(Video).order_by(Video.id.desc())).all()
    return [summarize_video(session, video) for video in videos]


def get_video(session: Session, video_id: int) -> VideoSummary | None:
    video = session.get(Video, video_id)
    return None if video is None else summarize_video(session, video)


def save_upload(
    session: Session,
    settings: Settings,
    filename: str,
    chunks: Iterable[bytes],
    name: str | None = None,
) -> VideoSummary:
    """Store an uploaded file under storage/uploads and register it.

    Only `.mp4` files are accepted, and the file must be a readable video (checked with ffprobe
    after it is written); otherwise the file is removed and `InvalidVideo` says why.
    """
    original = check_upload_name(filename)
    part = incoming_path(settings, original)
    written = 0
    with part.open("wb") as handle:
        for chunk in chunks:
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                handle.close()
                part.unlink(missing_ok=True)
                raise InvalidVideo("The file is larger than 8 GB. Register it where it lies with `tracko-anpr ingest`.")
            handle.write(chunk)
    return adopt_upload(session, settings, part, original, name=name)


def check_upload_name(filename: str) -> str:
    """The bare file name of an upload, refused with the reason unless it is an .mp4."""
    original = Path(filename).name or "upload.mp4"
    if Path(original).suffix.lower() != ".mp4":
        raise InvalidVideo(
            f"Only MP4 videos are accepted; '{original}' is not an .mp4 file. "
            "Convert it to H.264 MP4 with FFmpeg first."
        )
    return original


def incoming_path(settings: Settings, original: str) -> Path:
    """Where an upload is written while it arrives, before it is checked and given its final name."""
    folder = settings.uploads_dir / ".incoming"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{_clean_name(Path(original).stem)}-{os.getpid()}-{time.time_ns()}.part.mp4"


def adopt_upload(
    session: Session, settings: Settings, part: Path, original: str, name: str | None = None
) -> VideoSummary:
    """Check a fully written upload, move it to storage/uploads/<name>.mp4 and register it.

    The file must be a readable video (ffprobe); otherwise it is removed and `InvalidVideo` says why.
    """
    if not part.is_file() or part.stat().st_size == 0:
        part.unlink(missing_ok=True)
        raise InvalidVideo("The uploaded file is empty.")
    try:
        probe_video(part)
    except VideoError as error:
        part.unlink(missing_ok=True)
        raise InvalidVideo(f"'{original}' could not be read as a video: {error}") from error
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    final_name = _free_upload_name(session, settings, _clean_name(name or Path(original).stem))
    destination = settings.root / _upload_path(settings, final_name)
    shutil.move(part, destination)
    info = probe_video(destination)
    video = register_video(session, info, settings.root, UPLOADED, name=final_name, original_filename=original)
    return summarize_video(session, video)


def ingest_file(session: Session, settings: Settings, path: str | Path, name: str | None = None) -> VideoSummary:
    """Register a video that is already on disk, without copying it (for files too large to upload)."""
    try:
        info = probe_video(path)
    except VideoError as error:
        raise InvalidVideo(str(error)) from error
    video = register_video(session, info, settings.root, INGESTED, name=_clean_name(name) if name else None)
    return summarize_video(session, video)


def _upload_path(settings: Settings, name: str) -> str:
    return relative_path(settings.uploads_dir / f"{name}.mp4", settings.root)


def _free_upload_name(session: Session, settings: Settings, wanted: str) -> str:
    """A name no video has and no upload file uses: a second upload of 'clip.mp4' becomes 'clip-2'."""
    candidate, counter = wanted, 1
    while (
        session.scalar(select(Video.id).where(Video.name == candidate)) is not None
        or (settings.root / _upload_path(settings, candidate)).exists()
    ):
        counter += 1
        candidate = f"{wanted}-{counter}"
    return candidate


def _clean_name(name: str) -> str:
    """A folder-safe video name: letters, digits, dash, underscore and dot; never empty."""
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in name.strip()).strip("-.")
    return cleaned[:120] or "video"
