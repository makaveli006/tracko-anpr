"""Operators' corrections: saved beside the system's result, never over it. On SQLite, no model."""

from __future__ import annotations

import pytest
from result_builders import ROOT, a_result, video_info
from sqlalchemy import create_engine, select

from tracko_anpr.db import metrics
from tracko_anpr.db.models import COMMAND_LINE, PROCESSING, Base, RecognitionEvent, VehicleTrack
from tracko_anpr.db.session import make_session_factory, session_scope
from tracko_anpr.db.store import create_job, register_video, store_result
from tracko_anpr.services import corrections, results
from tracko_anpr.services.corrections import CorrectionError


@pytest.fixture
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def stored(session, name="clip_part01") -> int:
    video = register_video(session, video_info(name), ROOT, COMMAND_LINE)
    job = create_job(session, video, PROCESSING)
    store_result(session, job, a_result(video_info(name)), ROOT)
    return video.id


def track_pk_of(session, track_id: int) -> int:
    return session.scalar(select(VehicleTrack.id).where(VehicleTrack.track_id == track_id))


def test_a_correction_is_stored_beside_the_systems_result_and_the_figures_do_not_move(factory):
    with session_scope(factory) as session:
        video_id = stored(session)
        before = metrics.summary(session, video_id)
        pk = track_pk_of(session, 1)  # confirmed KL07AB1234
        made = corrections.save_correction(session, pk, "kl 07 ab 1284", None, corrected_by="Anand", note="4 not 3")
        assert made.corrected_number == "KL07AB1284" and made.corrected_type is None
        assert made.system_number == "KL07AB1234" and made.system_status == "confirmed" and made.system_type == "Car"
        assert made.number == "KL07AB1284" and made.vehicle_type == "Car"
        # the system's rows are untouched
        event = session.scalar(select(RecognitionEvent).where(RecognitionEvent.track_pk == pk))
        assert event.registration_number == "KL07AB1234" and event.status == "confirmed"
        assert metrics.summary(session, video_id) == before
        # the detail and the table rows carry it
        detail = results.detection_detail(session, pk)
        assert detail.detection.registration_number == "KL07AB1234"
        assert detail.correction.corrected_number == "KL07AB1284" and len(detail.corrections) == 1
        row = next(r for r in results.video_detections(session, video_id) if r.detection.track_pk == pk)
        assert row.correction.corrected_by == "Anand"


def test_type_only_corrections_and_the_history_newest_first(factory):
    with session_scope(factory) as session:
        stored(session)
        pk = track_pk_of(session, 3)  # Truck, no plate found
        first = corrections.save_correction(session, pk, None, "Bus")
        assert first.corrected_number is None and first.corrected_type == "Bus"
        second = corrections.save_correction(session, pk, "KL10ZZ0001", None)
        made = corrections.history(session, pk)
        assert [c.id for c in made] == [second.id, first.id]
        assert corrections.current_corrections(session, [pk])[pk].id == second.id
        assert corrections.undo_latest(session, pk) is True
        assert corrections.current_corrections(session, [pk])[pk].id == first.id
        assert corrections.undo_latest(session, pk) is True
        assert corrections.undo_latest(session, pk) is False
        assert corrections.current_corrections(session, [pk]) == {}


def test_corrections_are_refused_when_wrong_or_pointless(factory):
    with session_scope(factory) as session:
        stored(session)
        pk = track_pk_of(session, 1)
        with pytest.raises(CorrectionError, match="not a valid Indian registration number"):
            corrections.save_correction(session, pk, "HELLO", None)
        with pytest.raises(CorrectionError, match="Vehicle type must be one of"):
            corrections.save_correction(session, pk, None, "Tractor")
        with pytest.raises(CorrectionError, match="already the system's result"):
            corrections.save_correction(session, pk, "KL07AB1234", "Car")
        with pytest.raises(CorrectionError, match="already the system's result"):
            corrections.save_correction(session, pk, None, None)
        with pytest.raises(CorrectionError, match="not in the database"):
            corrections.save_correction(session, 99999, "KL07AB1299", None)
        assert corrections.history(session, pk) == []


def test_the_bharat_series_and_short_numbers_are_accepted(factory):
    with session_scope(factory) as session:
        stored(session)
        pk = track_pk_of(session, 2)
        assert corrections.save_correction(session, pk, "22 BH 1234 AB", None).corrected_number == "22BH1234AB"
        assert corrections.save_correction(session, pk, "kl39p77", None).corrected_number == "KL39P77"


def test_summary_counts_current_corrections_per_video_and_confirmed_numbers_changed(factory):
    with session_scope(factory) as session:
        one = stored(session, "one")
        two = stored(session, "two")
        tracks_one = {
            t.track_id: t.id for t in session.scalars(select(VehicleTrack).where(VehicleTrack.video_id == one))
        }
        corrections.save_correction(session, tracks_one[1], "KL07AB1284", None)  # confirmed number changed
        corrections.save_correction(session, tracks_one[1], "KL07AB1285", None)  # again: history of 2, current 1
        corrections.save_correction(session, tracks_one[2], None, "Car")  # type only, on an unconfirmed track
        all_videos = corrections.summary(session)
        assert all_videos.corrections == 3 and all_videos.tracks_corrected == 2
        assert all_videos.numbers_corrected == 1 and all_videos.types_corrected == 1
        assert all_videos.confirmed_numbers_changed == 1 and all_videos.confirmed_total == 4
        assert corrections.summary(session, two).tracks_corrected == 0
        assert [c.track_id for c in corrections.list_corrections(session, one)] == [2, 1]


def test_the_export_carries_the_corrections(factory):
    with session_scope(factory) as session:
        stored(session)
        pk = track_pk_of(session, 7)  # confirmed KL10CD5678
        corrections.save_correction(session, pk, "KL10CD5679", "Bus", corrected_by="Priya")
        text = results.export_history_csv(session)
        header, *lines = text.strip().splitlines()
        assert header.endswith("corrected_number,corrected_type,corrected_by,corrected_at")
        corrected = [line for line in lines if ",KL10CD5679,Bus,Priya," in line]
        assert len(corrected) == 1 and ",KL10CD5678,confirmed," in corrected[0]
        assert all(line.endswith(",,,") for line in lines if "T7," not in line)
