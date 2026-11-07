"""The processing worker: a separate process that takes queued jobs and runs the pipeline on them.

The `processing_jobs` table is the queue (ARCHITECTURE.md, "Job hand-off"). The web app only
inserts a row with status `queued`; this worker claims the oldest one, writes its stage and
progress back as it goes, and ends it as `completed` or `failed`. Video inference never runs
inside the web server.

What the worker guarantees:

- One job runs at a time, claimed with `SELECT ... FOR UPDATE SKIP LOCKED`, so two workers
  could not take the same job.
- Progress is written at every stage change and at least every few seconds, together with a
  heartbeat time, so the dashboard can tell a slow job from a dead worker.
- A job left at `processing` by a worker that died (power cut, kill -9) is found when the next
  worker starts: it goes back in the queue once, and its half-written result folders are
  removed; a job that has already been through that is failed with a message instead.
- The plate reader (a separate process, 20 seconds to start) is started once and kept for
  every job; if it dies, the client restarts it on the next request.
- A failure in one job (a corrupt file, a dead reader) is recorded on that job, and the worker
  carries on with the next.
"""

from __future__ import annotations

import os
import shutil
import socket
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tracko_anpr.config import Settings
from tracko_anpr.db.models import FAILED, PROCESSING, QUEUED, ProcessingJob, Video
from tracko_anpr.db.session import session_scope
from tracko_anpr.db.store import mark_failed, store_result
from tracko_anpr.pipeline.ocr_client import OcrClient
from tracko_anpr.services.readiness import record_worker_heartbeat

Logger = Callable[[str], None]


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


def video_file(video: Video, root: Path) -> Path:
    """The video's file on disk: `file_path` is relative to the project root unless it is absolute."""
    path = Path(video.file_path)
    return path if path.is_absolute() else root / path


def result_folders(settings: Settings, video_name: str) -> list[Path]:
    """The folders the pipeline writes for a video, which a run that will not finish leaves half-written."""
    return [
        settings.processed_dir / video_name,
        settings.vehicle_crops_dir / video_name,
        settings.plate_crops_dir / video_name,
    ]


def remove_result_folders(settings: Settings, video_name: str) -> None:
    for folder in result_folders(settings, video_name):
        shutil.rmtree(folder, ignore_errors=True)


class Worker:
    """Runs queued jobs until told to stop. One instance per worker process."""

    def __init__(
        self,
        settings: Settings,
        factory: sessionmaker[Session],
        worker_id: str | None = None,
        poll_seconds: float = 2.0,
        progress_seconds: float = 2.0,
        max_attempts: int = 2,
        log: Logger | None = None,
        run_pipeline: Callable | None = None,
        reader_factory: Callable[[], OcrClient] | None = None,
    ) -> None:
        self.settings = settings
        self.factory = factory
        self.worker_id = worker_id or default_worker_id()
        self.poll_seconds = poll_seconds
        self.progress_seconds = progress_seconds
        self.max_attempts = max_attempts
        self.log = log or (lambda message: None)
        self.reader: OcrClient | None = None
        self.stop_requested = threading.Event()
        # The pipeline and the reader are parameters so the worker's own logic can be tested without models.
        self._run_pipeline = run_pipeline
        self._reader_factory = reader_factory or self._project_reader

    # --- life cycle --------------------------------------------------------------------------

    def start(self) -> list[int]:
        """Prepare to work: recover jobs a dead worker left behind. Returns their ids."""
        recovered = self.recover_abandoned_jobs()
        self.log(f"worker {self.worker_id} ready" + (f"; recovered jobs {recovered}" if recovered else ""))
        return recovered

    def close(self) -> None:
        if self.reader is not None:
            self.reader.stop()
            self.reader = None

    def request_stop(self) -> None:
        """Finish the current job (if any), then stop. Safe to call from a signal handler."""
        self.stop_requested.set()

    def run_forever(self, once: bool = False) -> int:
        """Claim and run jobs until stopped. With `once`, run at most one job. Returns how many ran."""
        ran = 0
        try:
            while not self.stop_requested.is_set():
                self.heartbeat()
                job_id = self.claim_next_job()
                if job_id is None:
                    if once:
                        break
                    self.stop_requested.wait(self.poll_seconds)
                    continue
                self.run_job(job_id)
                ran += 1
                if once:
                    break
        finally:
            self.close()
        return ran

    def heartbeat(self) -> None:
        """Tell the dashboard a worker is alive, even with nothing to do (the status panel reads this)."""
        with session_scope(self.factory) as session:
            record_worker_heartbeat(session, self.worker_id)

    # --- the queue ---------------------------------------------------------------------------

    def recover_abandoned_jobs(self) -> list[int]:
        """Deal with jobs still marked `processing`: no worker is running them, since this one has just started.

        A job on its first attempt goes back to the queue; its half-written folders are removed so
        the retry starts clean. A job that has already been retried is failed, with the reason.
        """
        recovered: list[int] = []
        with session_scope(self.factory) as session:
            abandoned = session.scalars(
                select(ProcessingJob).where(ProcessingJob.status == PROCESSING).order_by(ProcessingJob.id)
            ).all()
            for job in abandoned:
                video_name = job.video.name
                remove_result_folders(self.settings, video_name)
                if job.attempts < self.max_attempts:
                    job.error = f"Worker {job.worker_id or '?'} stopped during attempt {job.attempts}; queued again."
                    job.status = QUEUED
                    job.stage = None
                    job.stage_done = job.stage_total = 0
                    job.started_at = job.heartbeat_at = None
                    job.worker_id = None
                    self.log(f"job {job.id} ({video_name}) was left half-done; back in the queue")
                else:
                    mark_failed(
                        session,
                        job,
                        f"The worker stopped while processing this video {job.attempts} times in a row "
                        "(out of memory or a crash in a model is the usual cause); the job was not retried again.",
                    )
                    self.log(f"job {job.id} ({video_name}) was left half-done for the {job.attempts}. time; failed")
                recovered.append(job.id)
        return recovered

    def claim_next_job(self) -> int | None:
        """Take the oldest queued job, marking it as this worker's. None when the queue is empty."""
        with session_scope(self.factory) as session:
            job = session.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.status == QUEUED)
                .order_by(ProcessingJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if job is None:
                return None
            job.status = PROCESSING
            job.worker_id = self.worker_id
            job.attempts += 1
            job.started_at = job.heartbeat_at = now()
            job.finished_at = None
            job.stage = "video_uploaded"
            job.stage_done = job.stage_total = 0
            job.error = None
            return job.id

    # --- one job -----------------------------------------------------------------------------

    def run_job(self, job_id: int) -> str:
        """Run the pipeline for one claimed job and record the outcome. Returns the final status."""
        with session_scope(self.factory) as session:
            job = session.get(ProcessingJob, job_id)
            video = job.video
            video_name, path = video.name, video_file(video, self.settings.root)
        self.log(f"job {job_id}: processing {video_name} ({path})")
        started = time.perf_counter()

        try:
            result = self._pipeline()(
                path,
                self.settings,
                None,
                self._progress_writer(job_id),
                name=video_name,
                reader=self._reader(),
            )
        except KeyboardInterrupt:
            self._requeue(job_id)
            self.log(f"job {job_id}: interrupted; back in the queue")
            raise
        except Exception as error:  # one bad video must not stop the worker
            message = f"{type(error).__name__}: {error}"
            remove_result_folders(self.settings, video_name)
            with session_scope(self.factory) as session:
                mark_failed(session, session.get(ProcessingJob, job_id), message)
            self.log(f"job {job_id}: failed after {time.perf_counter() - started:.0f} s: {message}")
            return FAILED

        with session_scope(self.factory) as session:
            job = session.get(ProcessingJob, job_id)
            store_result(session, job, result, self.settings.root)
            job.worker_id = self.worker_id
            status = job.status
        summary = result.summary
        self.log(
            f"job {job_id}: completed in {time.perf_counter() - started:.0f} s; "
            f"{summary['total_vehicles']} vehicles, {summary['confirmed']} confirmed plates"
        )
        return status

    def _progress_writer(self, job_id: int):
        """A stage-progress callback that writes to the job row, at most every `progress_seconds`."""
        state = {"stage": None, "written": 0.0}

        def report(stage: str, done: int, total: int) -> None:
            moment = time.monotonic()
            finished = total and done >= total
            if stage == state["stage"] and not finished and moment - state["written"] < self.progress_seconds:
                return
            state.update(stage=stage, written=moment)
            with session_scope(self.factory) as session:
                job = session.get(ProcessingJob, job_id)
                job.stage, job.stage_done, job.stage_total = stage, done, total
                job.heartbeat_at = now()

        return report

    def _requeue(self, job_id: int) -> None:
        with session_scope(self.factory) as session:
            job = session.get(ProcessingJob, job_id)
            job.status = QUEUED
            job.attempts = max(0, job.attempts - 1)  # an interruption asked for is not a crash
            job.stage = None
            job.stage_done = job.stage_total = 0
            job.started_at = job.heartbeat_at = None
            job.worker_id = None
            remove_result_folders(self.settings, job.video.name)

    def _reader(self) -> OcrClient:
        """The worker's own plate reader, created on first use and kept for later jobs."""
        if self.reader is None:
            self.reader = self._reader_factory()
        return self.reader

    def _project_reader(self) -> OcrClient:
        return OcrClient.for_project(
            self.settings.ocr_project,
            start_timeout=self.settings.ocr_start_timeout_seconds,
            request_timeout=self.settings.ocr_request_timeout_seconds,
        )

    def _pipeline(self) -> Callable:
        if self._run_pipeline is None:
            from tracko_anpr.pipeline.runner import run_pipeline  # loads PyTorch; imported only when needed

            self._run_pipeline = run_pipeline
        return self._run_pipeline


def now() -> datetime:
    return datetime.now(UTC)
