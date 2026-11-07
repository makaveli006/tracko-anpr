"""The database layer: storing a pipeline result and the metric queries built on the rows.

These run on an in-memory SQLite database, so they need no PostgreSQL. The models use JSONB
only on PostgreSQL and plain JSON elsewhere for that reason. The migrations themselves are
checked against the real database by hand (see ARCHITECTURE.md, Phase 8).
"""

from __future__ import annotations

from fractions import Fraction

import pytest
from result_builders import ROOT, a_result, video_info
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from tracko_anpr.db import metrics
from tracko_anpr.db.models import (
    COMMAND_LINE,
    COMPLETED,
    FAILED,
    PROCESSING,
    Base,
    PlateObservation,
    ProcessingJob,
    RecognitionEvent,
    VehicleTrack,
    Video,
)
from tracko_anpr.db.session import make_session_factory, session_scope
from tracko_anpr.db.store import create_job, mark_failed, register_video, store_result, unique_video_name
from tracko_anpr.pipeline.runner import PipelineResult, summarize
from tracko_anpr.pipeline.validation import CONFIRMED, NOT_DETECTED, UNCONFIRMED
from tracko_anpr.pipeline.video import VideoInfo


@pytest.fixture
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def store(session: Session, result: PipelineResult, name: str | None = None) -> ProcessingJob:
    video_row = register_video(session, result.info, ROOT, COMMAND_LINE, name=name)
    job = create_job(session, video_row, PROCESSING)
    store_result(session, job, result, ROOT)
    return job


# --- storing -------------------------------------------------------------------------------------


def test_a_run_is_stored_as_a_video_a_job_and_rows_per_track_plate_and_decision(factory):
    with session_scope(factory) as session:
        job = store(session, a_result())
        assert job.status == COMPLETED
        assert job.processing_seconds == 200.0
        assert job.annotated_video_path == "storage/processed/clip_part01/annotated.mp4"
        assert job.settings == {"vehicle_image_size": 1536}
        assert session.scalar(select(func.count()).select_from(Video)) == 1
        assert session.scalar(select(func.count()).select_from(VehicleTrack)) == 7
        assert session.scalar(select(func.count()).select_from(PlateObservation)) == 2
        # one per countable track, the repeat (T6) included: it keeps its number, it is just not counted again
        assert session.scalar(select(func.count()).select_from(RecognitionEvent)) == 5


def test_the_video_row_records_the_file_relative_to_the_project(factory):
    with session_scope(factory) as session:
        job = store(session, a_result())
        assert job.video.file_path == "videos/clip_part01.mp4"
        assert job.video.fps == "30"
        assert job.video.duration_s == 120.0


def test_track_rows_carry_the_counting_decisions(factory):
    with session_scope(factory) as session:
        store(session, a_result())
        by_id = {t.track_id: t for t in session.scalars(select(VehicleTrack)).all()}
        assert by_id[4].countable is False and by_id[4].counts_as_vehicle is False
        assert by_id[5].camera_car is True and by_id[5].counts_as_vehicle is False
        assert by_id[6].same_vehicle_as == 1 and by_id[6].counts_as_vehicle is False
        assert by_id[1].counts_as_vehicle is True
        assert by_id[1].first_seen_s == 0.0 and by_id[1].last_seen_s == 3.0


def test_the_decision_row_keeps_the_number_only_as_far_as_validation_supports_it(factory):
    with session_scope(factory) as session:
        store(session, a_result())
        events = {e.track.track_id: e for e in session.scalars(select(RecognitionEvent)).all()}
        assert events[1].status == CONFIRMED and events[1].registration_number == "KL07AB1234"
        assert events[2].status == UNCONFIRMED and events[2].registration_number == "KL39S3333"
        assert events[3].status == NOT_DETECTED and events[3].registration_number is None
        assert events[1].plate_crop_path == "storage/plate_crops/clip_part01/T1_f000030.png"


def test_processing_the_same_file_again_adds_a_job_to_the_same_video(factory):
    with session_scope(factory) as session:
        first = store(session, a_result())
        second = store(session, a_result())
        assert first.video_id == second.video_id
        assert session.scalar(select(func.count()).select_from(Video)) == 1
        assert session.scalar(select(func.count()).select_from(ProcessingJob)) == 2


def test_a_different_file_with_the_same_name_gets_a_distinct_video_name(factory):
    with session_scope(factory) as session:
        store(session, a_result())
        other = video_info()
        other = VideoInfo(ROOT / "elsewhere" / "clip_part01.mp4", 1920, 1080, Fraction(30), 3600, 120.0)
        assert unique_video_name(session, "clip_part01", "elsewhere/clip_part01.mp4") == "clip_part01-2"
        job = store(session, a_result(other))
        assert job.video.name == "clip_part01-2"


def test_a_failed_run_is_recorded_on_its_job(factory):
    with session_scope(factory) as session:
        video_row = register_video(session, video_info(), ROOT, COMMAND_LINE)
        job = create_job(session, video_row, PROCESSING)
        mark_failed(session, job, "OcrError: the reader died")
        assert job.status == FAILED
        assert job.error == "OcrError: the reader died"
        assert job.finished_at is not None


# --- the metrics ---------------------------------------------------------------------------------


def test_summary_counts_vehicles_tracks_and_confirmed_plates_like_the_pipeline(factory):
    result = a_result()
    with session_scope(factory) as session:
        store(session, result)
        overall = metrics.summary(session)
    assert overall.total_vehicles == result.summary["total_vehicles"] == 4
    assert overall.unique_tracks == result.summary["unique_tracks"] == 7
    assert overall.confirmed_plates == result.summary["confirmed"] == 2
    assert overall.recognition_coverage == result.summary["recognition_coverage"] == 0.5
    assert overall.videos_processed == 1
    assert overall.average_processing_seconds == 200.0
    assert overall.last_run_at is not None


def test_summary_is_empty_but_defined_on_an_empty_database(factory):
    with session_scope(factory) as session:
        overall = metrics.summary(session)
    assert overall.total_vehicles == 0 and overall.unique_tracks == 0 and overall.confirmed_plates == 0
    assert overall.recognition_coverage is None
    assert overall.videos_processed == 0
    assert overall.average_processing_seconds is None and overall.last_run_at is None


def test_a_reprocessed_video_shows_its_latest_completed_job_only(factory):
    with session_scope(factory) as session:
        store(session, a_result())
        smaller = a_result()
        smaller.vehicles = smaller.vehicles[:3]  # second run: only tracks 1 to 3
        smaller.summary = summarize(smaller.vehicles)
        store(session, smaller)
        overall = metrics.summary(session)
    assert overall.unique_tracks == 3
    assert overall.total_vehicles == 3
    assert overall.videos_processed == 1  # still one video


def test_a_job_still_running_is_not_part_of_any_figure(factory):
    with session_scope(factory) as session:
        store(session, a_result())
        video_row = session.scalar(select(Video))
        create_job(session, video_row, PROCESSING)  # a new run in progress
        overall = metrics.summary(session)
    assert overall.unique_tracks == 7


def test_figures_can_be_scoped_to_one_video_or_all(factory):
    with session_scope(factory) as session:
        first = store(session, a_result(video_info("one")))
        store(session, a_result(video_info("two")))
        assert metrics.summary(session).total_vehicles == 8
        assert metrics.summary(session, first.video_id).total_vehicles == 4
        assert metrics.summary(session).videos_processed == 2


def test_category_breakdown_lists_all_four_classes_over_counted_vehicles(factory):
    with session_scope(factory) as session:
        store(session, a_result())
        assert metrics.category_breakdown(session) == {"Car": 2, "Motorcycle": 1, "Bus": 0, "Truck": 1}


def test_validation_breakdown(factory):
    with session_scope(factory) as session:
        store(session, a_result())
        assert metrics.validation_breakdown(session) == {CONFIRMED: 2, UNCONFIRMED: 1, NOT_DETECTED: 1}


def test_detections_over_time_counts_each_vehicle_once_where_first_seen_and_adds_up(factory):
    with session_scope(factory) as session:
        job = store(session, a_result())
        buckets = metrics.detections_over_time(session, job.video_id)
    # 120 s video → 13 buckets (0 to 120 inclusive of the last partial one)
    assert [start for start, _ in buckets] == list(range(0, 130, 10))
    counts = dict(buckets)
    assert counts[0] == 1  # T1 at 0 s (the camera car and the brief track do not count)
    assert counts[10] == 1  # T2 at 10 s
    assert counts[20] == 1  # T3 at 23.3 s
    assert counts[110] == 1  # T7 at 110 s; T6 at 50 s is a repeat and is not counted
    assert sum(counts.values()) == metrics.summary(session).total_vehicles == 4


def test_detections_table_rows_newest_first_with_plate_and_crops(factory):
    with session_scope(factory) as session:
        store(session, a_result())
        rows = metrics.detections(session)
        assert [row.track_id for row in rows] == [7, 3, 2, 1]
        assert [row.track_id for row in metrics.detections(session, newest_first=False, limit=2)] == [1, 2]
        latest = rows[0]
        assert latest.video_name == "clip_part01"
        assert latest.vehicle_type == "Car"
        assert latest.status == CONFIRMED and latest.registration_number == "KL10CD5678"
        assert latest.plate_crop_path == "storage/plate_crops/clip_part01/T7_f003350.png"
        assert latest.vehicle_crop_path == "storage/vehicle_crops/clip_part01/T7.jpg"


def test_processing_durations_per_video(factory):
    with session_scope(factory) as session:
        store(session, a_result(video_info("one")))
        store(session, a_result(video_info("two")))
        assert metrics.processing_durations(session) == [("one", 200.0), ("two", 200.0)]
