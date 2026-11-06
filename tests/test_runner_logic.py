"""Tests for the runner's own logic and for plate drawing. No model, GPU or video is needed."""

from pathlib import Path

import numpy as np

from tracko_anpr.pipeline.annotate import (
    PLATE_COLOR,
    PlateLabel,
    draw_plates,
    format_plate_label,
)
from tracko_anpr.pipeline.runner import (
    NOT_COUNTED,
    STAGES,
    PlateSighting,
    VehicleRecord,
    best_plate_sighting,
    mark_repeat_tracks,
    plate_owner,
    settle_shared_numbers,
    summarize,
)
from tracko_anpr.pipeline.tracking import TrackedVehicle
from tracko_anpr.pipeline.validation import CONFIRMED, NOT_DETECTED, UNCONFIRMED, PlateDecision


def vehicle(track_id, class_name="Car", countable=True, camera_car=False, status=None, text=""):
    decision = None if status is None else PlateDecision(status, text=text, confidence=0.9)
    return VehicleRecord(track_id, class_name, 0, 10, 11, 0.9, countable, camera_car, decision)


def sighting(text, confidence, detector_confidence=0.8, frame=0):
    return PlateSighting(
        1, frame, (0.0, 0.0, 10.0, 5.0), detector_confidence, Path(f"T1_f{frame}.png"), text, confidence
    )


# --- the seven stages ---------------------------------------------------------------------------


def test_the_stages_match_the_dashboard_timeline_in_order():
    assert STAGES == (
        "video_uploaded",
        "vehicle_detection",
        "vehicle_tracking",
        "plate_detection",
        "ocr",
        "validation",
        "result_generation",
    )


# --- headline figures ---------------------------------------------------------------------------


def test_summary_counts_only_countable_vehicles_and_reports_the_rest_beside_them():
    vehicles = [
        vehicle(1, "Car", status=CONFIRMED, text="KL07CN9092"),
        vehicle(2, "Car", status=UNCONFIRMED, text="KL57B1883"),
        vehicle(3, "Motorcycle", status=NOT_DETECTED),
        vehicle(4, "Bus", status=NOT_DETECTED),
        vehicle(5, "Car", countable=False),  # glimpsed for a few frames
        vehicle(6, "Truck", countable=False, camera_car=True),  # the camera car's bonnet
    ]
    summary = summarize(vehicles)
    assert summary["unique_tracks"] == 6
    assert summary["total_vehicles"] == 4
    assert summary["tracks_too_brief_or_small"] == 1
    assert summary["camera_car_tracks"] == 1
    assert summary["by_class"] == {"Car": 2, "Motorcycle": 1, "Bus": 1, "Truck": 0}
    assert (summary["confirmed"], summary["unconfirmed"], summary["not_detected"]) == (1, 1, 2)
    assert summary["recognition_coverage"] == 0.25


def test_coverage_is_confirmed_plates_over_countable_vehicles_never_over_all_tracks():
    vehicles = [vehicle(1, status=CONFIRMED, text="KL07CN9092")] + [vehicle(n, countable=False) for n in range(2, 12)]
    assert summarize(vehicles)["recognition_coverage"] == 1.0


def test_with_no_countable_vehicles_coverage_is_absent_not_zero():
    summary = summarize([vehicle(1, countable=False)])
    assert summary["total_vehicles"] == 0
    assert summary["recognition_coverage"] is None
    assert summarize([])["recognition_coverage"] is None


def test_a_track_that_is_not_counted_has_no_plate_status():
    assert vehicle(1, countable=False).status == NOT_COUNTED
    assert vehicle(1, status=CONFIRMED).status == CONFIRMED


# --- the same vehicle under two track numbers ---------------------------------------------------


def seen(track_id, first, last, text="KL07CS2700", status=CONFIRMED, countable=True):
    record = vehicle(track_id, status=status, text=text, countable=countable)
    record.first_frame, record.last_frame = first, last
    return record


def test_a_later_track_with_the_same_confirmed_number_is_the_same_vehicle():
    vehicles = [seen(58, 100, 200), seen(69, 400, 500), seen(80, 900, 950)]
    mark_repeat_tracks(vehicles)
    assert [v.same_vehicle_as for v in vehicles] == [None, 58, 58]
    summary = summarize(vehicles)
    assert summary["unique_tracks"] == 3
    assert summary["total_vehicles"] == 1
    assert summary["repeat_tracks"] == 2
    assert summary["confirmed"] == 1
    assert summary["recognition_coverage"] == 1.0


def test_order_of_appearance_decides_which_track_is_the_first():
    vehicles = [seen(69, 400, 500), seen(58, 100, 200)]
    mark_repeat_tracks(vehicles)
    assert [(v.track_id, v.same_vehicle_as) for v in vehicles] == [(69, 58), (58, None)]


def test_tracks_that_overlap_in_time_are_not_merged():
    # One vehicle cannot be in two places at once, so one of these is a misreading.
    vehicles = [seen(1, 100, 300), seen(2, 200, 400)]
    mark_repeat_tracks(vehicles)
    assert [v.same_vehicle_as for v in vehicles] == [None, None]
    assert summarize(vehicles)["total_vehicles"] == 2


def test_only_confirmed_numbers_merge_tracks():
    vehicles = [seen(1, 100, 200, status=UNCONFIRMED), seen(2, 400, 500, status=UNCONFIRMED)]
    mark_repeat_tracks(vehicles)
    assert [v.same_vehicle_as for v in vehicles] == [None, None]


def test_different_numbers_are_different_vehicles():
    vehicles = [seen(1, 100, 200, text="KL07CS2700"), seen(2, 400, 500, text="KL07CX3928")]
    mark_repeat_tracks(vehicles)
    assert [v.same_vehicle_as for v in vehicles] == [None, None]


# --- whose plate it is --------------------------------------------------------------------------

# Taken from kochi_part02: a van seen from the side (T271), whose box also covers the back of
# the car ahead of it (T213), and a motorcycle (T357) in front of a car (T358).
VAN, CAR_AHEAD = (1441.7, 484.9, 2513.4, 1059.9), (1300.0, 800.0, 1620.0, 1080.0)
MOTORCYCLE, CAR_BEHIND = (1377.0, 898.7, 1671.7, 1335.9), (1569.9, 768.2, 2166.2, 1177.8)


def test_a_plate_inside_a_smaller_overlapping_vehicle_belongs_to_that_vehicle():
    plate = (1405.7, 975.1, 1533.0, 1015.0)
    assert plate_owner(plate, 271, {271: VAN, 213: CAR_AHEAD}) == 213


def test_the_smaller_vehicle_keeps_its_own_plate_whichever_cut_out_it_was_found_in():
    plate = (1544.4, 1137.8, 1634.9, 1200.6)
    boxes = {357: MOTORCYCLE, 358: CAR_BEHIND}
    assert plate_owner(plate, 357, boxes) == 357
    assert plate_owner(plate, 358, boxes) == 357


def test_a_plate_outside_every_other_vehicle_stays_with_the_one_it_was_found_in():
    plate = (1939.8, 875.2, 2022.2, 900.6)
    assert plate_owner(plate, 271, {271: VAN, 213: CAR_AHEAD}) == 271
    assert plate_owner(plate, 271, {271: VAN}) == 271
    assert plate_owner(plate, 271, {}) == 271


def test_a_larger_vehicle_around_the_plate_does_not_take_it():
    plate = (1420.0, 1000.0, 1520.0, 1030.0)
    assert plate_owner(plate, 213, {271: VAN, 213: CAR_AHEAD}) == 213


def test_a_plate_in_the_padding_just_outside_its_own_box_is_still_its_own():
    plate = (1380.0, 990.0, 1440.0, 1010.0)  # centre left of the van's box, inside its padded cut-out
    assert plate_owner(plate, 271, {271: VAN}) == 271


# --- one number, two vehicles in view at once ---------------------------------------------------


def backed(track_id, first, last, support, confidence=0.9, text="KL36F747"):
    record = vehicle(track_id)
    record.first_frame, record.last_frame = first, last
    record.decision = PlateDecision(CONFIRMED, text=text, confidence=confidence, support=support)
    return record


def test_of_two_vehicles_in_view_together_only_the_better_supported_keeps_the_number():
    vehicles = [backed(271, 100, 300, support=2), backed(279, 200, 400, support=5)]
    settle_shared_numbers(vehicles)
    assert [v.status for v in vehicles] == [UNCONFIRMED, CONFIRMED]
    assert vehicles[0].decision.text == "KL36F747"  # the reading is kept, only its standing changes
    assert "T279" in vehicles[0].decision.reason
    assert summarize(vehicles)["confirmed"] == 1


def test_equal_support_is_settled_by_confidence():
    vehicles = [backed(1, 100, 300, support=3, confidence=0.88), backed(2, 200, 400, support=3, confidence=0.93)]
    settle_shared_numbers(vehicles)
    assert [v.status for v in vehicles] == [UNCONFIRMED, CONFIRMED]


def test_the_same_number_at_different_times_is_left_confirmed_for_the_repeat_rule():
    vehicles = [backed(58, 100, 200, support=2), backed(69, 400, 500, support=4)]
    settle_shared_numbers(vehicles)
    mark_repeat_tracks(vehicles)
    assert [v.status for v in vehicles] == [CONFIRMED, CONFIRMED]
    assert [v.same_vehicle_as for v in vehicles] == [None, 58]


def test_different_numbers_in_view_together_are_untouched():
    vehicles = [backed(1, 100, 300, support=2), backed(2, 200, 400, support=2, text="KL07CV4602")]
    settle_shared_numbers(vehicles)
    assert [v.status for v in vehicles] == [CONFIRMED, CONFIRMED]


# --- which crop represents the plate ------------------------------------------------------------


def test_the_representative_crop_agrees_with_the_decision_when_one_does():
    decision = PlateDecision(CONFIRMED, text="KL07CN9092", confidence=0.9)
    sightings = [sighting("DL07CN9092", 0.95, frame=1), sighting("KL07CN9092", 0.88, frame=2)]
    assert best_plate_sighting(sightings, decision).frame == 2


def test_a_corrected_reading_counts_as_agreeing():
    decision = PlateDecision(CONFIRMED, text="KL10AB1234", confidence=0.9)
    sightings = [sighting("XYZ", 0.99, frame=1), sighting("KL10A81234", 0.80, frame=2)]
    assert best_plate_sighting(sightings, decision).frame == 2


def test_without_agreement_the_most_confident_crop_is_used_and_none_when_there_are_no_crops():
    undecided = PlateDecision(UNCONFIRMED)
    sightings = [sighting("", 0.4, frame=1), sighting("", 0.7, frame=2)]
    assert best_plate_sighting(sightings, undecided).frame == 2
    assert best_plate_sighting([], undecided) is None


# --- drawing plates -----------------------------------------------------------------------------


def test_plate_label_text_shows_confidence_only_once_confirmed():
    assert format_plate_label(PlateLabel("KL10AB1234", 0.97, confirmed=True)) == "KL10AB1234 (0.97)"
    assert format_plate_label(PlateLabel("KL10AB1234", 0.71, confirmed=False)) == "KL10AB1234 unconfirmed"


def test_a_located_plate_gets_an_amber_outline_and_vehicles_without_a_number_get_nothing():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    vehicles = [
        TrackedVehicle(1, "Car", 0.9, (400.0, 300.0, 900.0, 700.0)),
        TrackedVehicle(2, "Car", 0.9, (1200.0, 300.0, 1700.0, 700.0)),
    ]
    draw_plates(frame, vehicles, {1: PlateLabel("KL10AB1234", 0.97, True)}, {1: (600.0, 600.0, 700.0, 630.0)})
    assert tuple(frame[615, 600]) == PLATE_COLOR  # left edge of the plate outline
    assert not frame[:, 1200:].any()  # vehicle 2 has no number: nothing drawn for it


def test_a_number_is_still_shown_when_the_plate_is_not_located_in_this_frame():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    vehicles = [TrackedVehicle(1, "Car", 0.9, (400.0, 300.0, 900.0, 700.0))]
    draw_plates(frame, vehicles, {1: PlateLabel("KL10AB1234", 0.97, True)}, {})
    assert frame[640:700, 400:900].any()  # written inside the bottom of the vehicle's box
    assert not frame[:300].any()


def test_plate_drawing_stays_inside_the_frame_at_the_edges():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    vehicles = [TrackedVehicle(1, "Car", 0.9, (100.0, 80.0, 159.0, 119.0))]
    draw_plates(frame, vehicles, {1: PlateLabel("KL10AB1234", 0.5, False)}, {1: (140.0, 110.0, 159.0, 119.0)})
    assert frame.shape == (120, 160, 3)
    assert frame.any()
