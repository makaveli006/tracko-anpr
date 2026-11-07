"""The worker's own logic: claiming, progress, outcomes and crash recovery.

The pipeline is replaced by a small function, so these need no models and no PostgreSQL
(an in-memory SQLite database stands in). The real run, and killing a worker mid-job, were
done by hand against PostgreSQL; see ARCHITECTURE.md, Phase 9.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from result_builders import a_result, video_info
from sqlalchemy import create_engine, func, select

from tracko_anpr.config import load_settings
from tracko_anpr.db.models import COMPLETED, FAILED, PROCESSING, QUEUED, Base, ProcessingJob, VehicleTrack
from tracko_anpr.db.session import make_session_factory, session_scope
from tracko_anpr.db.store import create_job, queue_job, register_video
from tracko_anpr.pipeline.video import VideoError
from tracko_anpr.worker.service import Worker, remove_result_folders, result_folders


@pytest.fixture
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def settings(tmp_path):
    return load_settings(root=tmp_path, environ={})


def fake_pipeline(calls: list | None = None, fail_with: Exception | None = None):
    """Stands in for run_pipeline: reports a little progress, then returns a result or raises."""
    calls = calls if calls is not None else []

    def run(video, settings, options, progress, name=None, reader=None):
        calls.append({"video": Path(video), "name": name, "reader": reader})
        progress("video_uploaded", 1, 1)
        progress("vehicle_detection", 50, 100)
        progress("vehicle_detection", 100, 100)
        if fail_with is not None:
            raise fail_with
        return a_result(video_info(name or "clip_part01"))

    return run


def queued(factory, settings, name="clip_part01") -> int:
    with session_scope(factory) as session:
        video = register_video(session, video_info(name), settings.root, "ingest")
        job, _ = queue_job(session, video)
        return job.id


def job_row(factory, job_id) -> ProcessingJob:
    with session_scope(factory) as session:
        return session.get(ProcessingJob, job_id)


class FakeReader:
    """Stands in for the plate reader process; the fake pipeline never reads anything."""

    stopped = False

    def stop(self) -> None:
        self.stopped = True


def worker(factory, settings, pipeline=None, **options) -> Worker:
    return Worker(
        settings,
        factory,
        worker_id="test-1",
        run_pipeline=pipeline or fake_pipeline(),
        reader_factory=FakeReader,
        **options,
    )


# --- the queue -----------------------------------------------------------------------------------


def test_queueing_a_video_twice_reuses_its_pending_job(factory, settings):
    first = queued(factory, settings)
    second = queued(factory, settings)
    assert first == second
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(ProcessingJob)) == 1


def test_the_oldest_queued_job_is_claimed_first_and_marked_as_this_workers(factory, settings):
    first = queued(factory, settings, "one")
    queued(factory, settings, "two")
    claimed = worker(factory, settings).claim_next_job()
    assert claimed == first
    job = job_row(factory, claimed)
    assert job.status == PROCESSING
    assert job.worker_id == "test-1"
    assert job.attempts == 1
    assert job.started_at is not None and job.heartbeat_at is not None


def test_an_empty_queue_gives_nothing_and_once_returns_at_once(factory, settings):
    w = worker(factory, settings)
    assert w.claim_next_job() is None
    assert w.run_forever(once=True) == 0


# --- one job -------------------------------------------------------------------------------------


def test_a_job_runs_the_pipeline_on_the_videos_file_under_its_name_and_completes(factory, settings):
    job_id = queued(factory, settings)
    calls: list = []
    w = worker(factory, settings, fake_pipeline(calls))
    assert w.run_forever(once=True) == 1
    assert calls[0]["video"] == Path("/project/videos/clip_part01.mp4")  # outside the root, so kept absolute
    assert calls[0]["name"] == "clip_part01"
    assert isinstance(calls[0]["reader"], FakeReader)  # the worker's own reader, handed to the pipeline
    assert calls[0]["reader"].stopped  # ...and stopped when the worker finished
    job = job_row(factory, job_id)
    assert job.status == COMPLETED
    assert job.processing_seconds == 200.0
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(VehicleTrack)) == 7


def test_progress_and_heartbeat_are_written_to_the_job_as_it_runs(factory, settings):
    seen: list[tuple] = []
    job_id = queued(factory, settings)

    def spying_pipeline(video, settings_, options, progress, name=None, reader=None):
        progress("plate_detection", 3, 10)
        seen.append(tuple((j.stage, j.stage_done, j.stage_total) for j in [job_row(factory, job_id)]))
        progress("plate_detection", 10, 10)
        seen.append(tuple((j.stage, j.stage_done, j.stage_total) for j in [job_row(factory, job_id)]))
        return a_result(video_info(name))

    w = worker(factory, settings, spying_pipeline)
    w.run_forever(once=True)
    assert seen[0] == (("plate_detection", 3, 10),)
    assert seen[1] == (("plate_detection", 10, 10),)  # the end of a stage is always written
    assert job_row(factory, job_id).heartbeat_at is not None


def test_a_corrupt_video_ends_as_failed_with_the_reason_and_the_worker_carries_on(factory, settings):
    bad = queued(factory, settings, "broken")
    good = queued(factory, settings, "fine")
    outcomes = iter([VideoError("No frames could be read from broken.mp4."), None])

    def flaky(video, settings_, options, progress, name=None, reader=None):
        error = next(outcomes)
        if error is not None:
            for folder in result_folders(settings_, name):
                folder.mkdir(parents=True, exist_ok=True)  # half-written output
            raise error
        return a_result(video_info(name))

    w = worker(factory, settings, flaky)
    w.run_forever(once=True)
    w.run_forever(once=True)
    failed = job_row(factory, bad)
    assert failed.status == FAILED
    assert failed.error == "VideoError: No frames could be read from broken.mp4."
    assert failed.finished_at is not None
    assert not any(folder.exists() for folder in result_folders(settings, "broken"))
    assert job_row(factory, good).status == COMPLETED


def test_an_interrupted_job_goes_back_in_the_queue_without_counting_as_a_crash(factory, settings):
    job_id = queued(factory, settings)
    w = worker(factory, settings, fake_pipeline(fail_with=KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        w.run_forever(once=True)
    job = job_row(factory, job_id)
    assert job.status == QUEUED
    assert job.attempts == 0
    assert job.worker_id is None


# --- recovery after a crash ----------------------------------------------------------------------


def abandoned_job(factory, settings, attempts: int) -> int:
    """A job a dead worker left at `processing`, with half-written folders on disk."""
    with session_scope(factory) as session:
        video = register_video(session, video_info("left_behind"), settings.root, "ingest")
        job = create_job(session, video, PROCESSING)
        job.attempts = attempts
        job.worker_id = "dead-worker"
        job.stage = "vehicle_detection"
        job_id = job.id
    for folder in result_folders(settings, "left_behind"):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "partial.txt").write_text("half")
    return job_id


def test_a_job_left_half_done_goes_back_in_the_queue_once_with_its_folders_removed(factory, settings):
    job_id = abandoned_job(factory, settings, attempts=1)
    w = worker(factory, settings)
    assert w.start() == [job_id]
    job = job_row(factory, job_id)
    assert job.status == QUEUED
    assert job.worker_id is None and job.stage is None
    assert "dead-worker" in job.error
    assert not any(folder.exists() for folder in result_folders(settings, "left_behind"))
    # ...and the retry then runs to completion
    w.run_forever(once=True)
    job = job_row(factory, job_id)
    assert job.status == COMPLETED and job.attempts == 2


def test_a_job_that_already_crashed_a_worker_once_is_failed_the_second_time(factory, settings):
    job_id = abandoned_job(factory, settings, attempts=2)
    worker(factory, settings).start()
    job = job_row(factory, job_id)
    assert job.status == FAILED
    assert "2 times" in job.error
    assert not any(folder.exists() for folder in result_folders(settings, "left_behind"))


def test_recovery_leaves_queued_completed_and_failed_jobs_alone(factory, settings):
    queued(factory, settings, "waiting")
    worker(factory, settings).run_forever(once=True)  # one completed
    with session_scope(factory) as session:
        statuses_before = sorted(session.scalars(select(ProcessingJob.status)).all())
    assert worker(factory, settings).start() == []
    with session_scope(factory) as session:
        assert sorted(session.scalars(select(ProcessingJob.status)).all()) == statuses_before


def test_removing_result_folders_that_do_not_exist_is_fine(settings):
    remove_result_folders(settings, "never_processed")
