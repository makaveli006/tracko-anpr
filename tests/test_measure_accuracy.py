"""The counting behind the accuracy figures (tools/measure_accuracy.py), on made-up rows."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "measure_accuracy", Path(__file__).resolve().parents[1] / "tools" / "measure_accuracy.py"
)
measure_accuracy = importlib.util.module_from_spec(spec)
import sys  # noqa: E402

sys.modules["measure_accuracy"] = measure_accuracy
spec.loader.exec_module(measure_accuracy)


def answer(track, number, status, vehicle_type="Car"):
    return {"track": track, "registration_number": number, "status": status, "vehicle_type": vehicle_type}


def label(track, number, legible="yes", vehicle_type="Car", is_vehicle="yes", duplicate=""):
    return {
        "note": "",
        "track": track,
        "true_number": number,
        "plate_legible": legible,
        "true_type": vehicle_type,
        "is_vehicle": is_vehicle,
        "duplicate_of": duplicate,
    }


def test_confirmed_numbers_are_split_into_correct_wrong_and_not_checkable():
    system = [
        answer("T1", "KL07AB1234", "confirmed"),
        answer("T2", "KL07AB1284", "confirmed"),
        answer("T3", "KL10CD5678", "confirmed"),
    ]
    truth = [label("T1", "KL07AB1234"), label("T2", "KL07AB1234"), label("T3", "KL10?D5678", "partly")]
    m = measure_accuracy.measure(system, truth)
    assert (m.confirmed, m.correct, len(m.wrong), len(m.not_checkable)) == (3, 1, 1, 1)
    assert m.accuracy == 0.5  # a partly legible plate proves nothing either way
    assert m.wrong[0]["character_errors"] == 1
    assert m.readable == 2 and m.recall == 0.5


def test_repeats_and_false_tracks_stay_out_of_the_figures_but_are_reported():
    system = [
        answer("T1", "KL07AB1234", "confirmed"),
        answer("T2", "KL07AB1234", "confirmed"),
        answer("T3", "", "not_detected"),
    ]
    truth = [
        label("T1", "KL07AB1234"),
        label("T2", "KL07AB1234", duplicate="T1"),
        label("T3", "", "no", is_vehicle="no"),
    ]
    m = measure_accuracy.measure(system, truth)
    assert (m.vehicles, m.duplicates, m.false_tracks) == (1, 1, 1)
    assert m.confirmed == 1 and len(m.confirmed_on_duplicates) == 1


def test_a_track_the_system_merged_away_is_a_repeat_or_a_lost_vehicle():
    system = [answer("T1", "KL07AB1234", "confirmed")]
    truth = [label("T1", "KL07AB1234"), label("T2", "KL07AB1234", duplicate="T1"), label("T3", "", "no")]
    m = measure_accuracy.measure(system, truth)
    assert m.merged_by_system == 2 and m.duplicates == 1
    assert m.vehicles == 2 and [row["track"] for row in m.lost_vehicles] == ["T3"]
    assert m.correct == 1


def test_unconfirmed_vehicles_are_sorted_by_what_their_guess_was_worth():
    system = [
        answer("T1", "KL07AB1234", "unconfirmed"),
        answer("T2", "KL07AB9999", "unconfirmed"),
        answer("T3", "", "not_detected"),
        answer("T4", "KL10CD5678", "unconfirmed"),
    ]
    truth = [label("T1", "KL07AB1234"), label("T2", "KL07AB1234"), label("T3", "", "no"), label("T4", "", "no")]
    m = measure_accuracy.measure(system, truth)
    assert m.unconfirmed == {"right number": 1, "wrong number": 1, "no number": 1, "not checkable": 1}
    assert m.confirmed == 0 and m.accuracy is None
    assert m.readable == 2 and m.recall == 0.0  # right but unconfirmed does not count as found


def test_type_errors_and_the_report_with_its_margin():
    m = measure_accuracy.measure([answer("T1", "KL07AB1234", "confirmed", "Truck")], [label("T1", "KL07AB1234")])
    assert m.type_errors[0]["system_type"] == "Truck"
    text = measure_accuracy.report(m)
    assert "100% ±100 points (n=1)" in text and "Type errors" in text
    assert measure_accuracy.margin(16) == pytest.approx(0.25)
    assert measure_accuracy.margin(0) is None
