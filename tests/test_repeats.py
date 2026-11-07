"""Parked vehicles under several track ids, and the camera movement behind the rule. No model is needed."""

from __future__ import annotations

import numpy as np
import pytest

from tracko_anpr.pipeline.repeats import ParkedRules, ParkedTrack, colour_look, overlap, parked_groups
from tracko_anpr.pipeline.runner import VehicleRecord, mark_parked_repeats, parked_track
from tracko_anpr.pipeline.tracking import CameraPath
from tracko_anpr.pipeline.validation import CONFIRMED, UNCONFIRMED, PlateDecision

BOX = (100.0, 100.0, 300.0, 200.0)


def look(blue: int, green: int, red: int) -> np.ndarray:
    return colour_look(np.full((40, 40, 3), (blue, green, red), dtype=np.uint8))


RED, GREEN = look(30, 30, 220), look(30, 220, 30)


def track(track_id, first, last, box=BOX, drift=0.0, colour=RED, number=None) -> ParkedTrack:
    return ParkedTrack(track_id, first, last, box, drift, colour, number)


def ids(groups) -> list[list[int]]:
    return [[t.track_id for t in group] for group in groups]


def test_a_parked_vehicle_under_three_tracks_is_one_group():
    assert ids(parked_groups([track(1, 0, 50), track(5, 80, 120), track(9, 200, 260)])) == [[1, 5, 9]]


def test_tracks_in_view_at_the_same_time_are_two_vehicles():
    assert parked_groups([track(1, 0, 100), track(2, 50, 150)]) == []
    # nor can a third track join them into one group through a track that overlaps neither
    groups = ids(parked_groups([track(1, 0, 100), track(2, 50, 150), track(3, 200, 250)]))
    assert groups == [[1, 3]]


def test_a_track_that_moved_is_not_parked():
    assert parked_groups([track(1, 0, 50, drift=0.2), track(2, 80, 120)]) == []


def test_a_different_place_or_colour_is_a_different_vehicle():
    assert parked_groups([track(1, 0, 50), track(2, 80, 120, box=(600.0, 100.0, 800.0, 200.0))]) == []
    assert parked_groups([track(1, 0, 50), track(2, 80, 120, colour=GREEN)]) == []
    assert parked_groups([track(1, 0, 50), track(2, 80, 120, colour=None)]) == []


def test_two_different_confirmed_numbers_are_never_one_vehicle():
    tracks = [track(1, 0, 50, number="KL07AB1234"), track(2, 80, 120, number="KL10CD5678")]
    assert parked_groups(tracks) == []
    assert parked_groups([track(1, 0, 50, number="KL07AB1234"), track(2, 80, 120)]) != []


def test_the_rules_can_be_tightened():
    near = (120.0, 100.0, 320.0, 200.0)
    assert overlap(BOX, near) == pytest.approx(180 / 220)
    tracks = [track(1, 0, 50), track(2, 80, 120, box=near)]
    assert parked_groups(tracks) != []
    assert parked_groups(tracks, ParkedRules(min_overlap=0.9)) == []


def textured(shift_x: int = 0, shift_y: int = 0) -> np.ndarray:
    random = np.random.default_rng(7)
    picture = np.repeat(np.repeat(random.integers(0, 255, (90, 160)), 12, axis=0), 12, axis=1).astype(np.uint8)
    picture = np.roll(picture, (shift_y, shift_x), axis=(0, 1))
    return np.dstack([picture] * 3)


def test_the_camera_path_follows_the_pictures_movement_in_original_pixels():
    camera = CameraPath(step=2)
    camera.record(0, textured())
    camera.record(1, textured(400, 0))  # not a sampled frame: ignored
    camera.record(2, textured(48, 24))
    assert camera.at(0) == (0.0, 0.0)
    x, y = camera.at(3)  # between samples: the last one
    assert x == pytest.approx(48, abs=6) and y == pytest.approx(24, abs=6)


def vehicle(track_id, first, last, decision=None, crop=None) -> VehicleRecord:
    return VehicleRecord(
        track_id, "Car", first, last, last - first + 1, 0.9, True, False, decision=decision, vehicle_crop=crop
    )


def write_crop(folder, name, colour):
    import cv2

    path = folder / f"{name}.jpg"
    cv2.imwrite(str(path), np.full((60, 60, 3), colour, dtype=np.uint8))
    return path


def sightings(first, last, box=BOX):
    return [(frame, box) for frame in range(first, last + 1)]


def test_the_confirmed_track_stays_counted_and_the_others_point_to_it(tmp_path):
    crop = write_crop(tmp_path, "red", (30, 30, 220))
    number = PlateDecision(CONFIRMED, "KL84F8061", 0.9, 3, 3, 1.0)
    unsure = PlateDecision(UNCONFIRMED, "", 0.0, 0, 0, 0.0)
    records = [vehicle(1, 0, 20, unsure, crop), vehicle(2, 40, 60, number, crop), vehicle(3, 80, 100, unsure, crop)]
    history = {1: sightings(0, 20), 2: sightings(40, 60), 3: sightings(80, 100)}
    mark_parked_repeats(records, history, CameraPath(), 1920)
    assert [r.same_vehicle_as for r in records] == [2, None, 2]
    assert [r.counts_as_vehicle for r in records] == [False, True, False]


def test_without_a_confirmed_number_the_earliest_track_stays_counted(tmp_path):
    crop = write_crop(tmp_path, "red", (30, 30, 220))
    records = [vehicle(1, 0, 20, crop=crop), vehicle(2, 40, 60, crop=crop)]
    mark_parked_repeats(records, {1: sightings(0, 20), 2: sightings(40, 60)}, CameraPath(), 1920)
    assert [r.same_vehicle_as for r in records] == [None, 1]


def test_a_track_already_marked_as_a_repeat_is_left_alone(tmp_path):
    crop = write_crop(tmp_path, "red", (30, 30, 220))
    records = [vehicle(1, 0, 20, crop=crop), vehicle(2, 40, 60, crop=crop)]
    records[1].same_vehicle_as = 9
    mark_parked_repeats(records, {1: sightings(0, 20), 2: sightings(40, 60)}, CameraPath(), 1920)
    assert [r.same_vehicle_as for r in records] == [None, 9]


def test_the_cameras_movement_is_taken_out_of_a_parked_vehicles_position(tmp_path):
    crop = write_crop(tmp_path, "red", (30, 30, 220))
    camera = CameraPath(step=1)
    camera.positions = {frame: (frame * 10.0, 0.0) for frame in range(100)}
    moving_in_picture = [(frame, (100.0 + frame * 10, 100.0, 300.0 + frame * 10, 200.0)) for frame in range(50)]
    parked = parked_track(vehicle(1, 0, 49, crop=crop), moving_in_picture, camera, 1920)
    assert parked.drift == pytest.approx(0.0, abs=0.001)
    assert parked.box == pytest.approx(BOX)
    still = parked_track(vehicle(1, 0, 49, crop=crop), moving_in_picture, CameraPath(), 1920)
    assert still.drift > 0.1
