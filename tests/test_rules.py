import pytest

from tracko_anpr.pipeline.rules import TrackRules, is_camera_car, is_countable


def track(frames: int, box, start: int = 0):
    return [(start + index, box) for index in range(frames)]


# --- which tracks count as vehicles ------------------------------------------------------------


@pytest.mark.parametrize(("fps", "height"), [(30.0, 1080), (60.0, 1080), (30.0, 1440), (59.94, 1440)])
def test_a_vehicle_followed_for_a_second_and_near_enough_counts_at_any_resolution_and_frame_rate(fps, height):
    tall_enough = (100.0, 100.0, 300.0, 100.0 + 0.1 * height)
    assert is_countable(track(round(fps), tall_enough), height, fps)


def test_a_vehicle_glimpsed_for_a_few_frames_does_not_count():
    box = (100.0, 100.0, 300.0, 400.0)
    assert not is_countable(track(10, box), 1080, 30.0)  # a third of a second
    assert is_countable(track(15, box), 1080, 30.0)  # half a second
    # The same number of frames is half as long at 60 FPS.
    assert not is_countable(track(15, box), 1080, 60.0)


def test_a_vehicle_that_never_comes_near_does_not_count():
    speck = (100.0, 100.0, 140.0, 130.0)  # 30 px tall
    assert not is_countable(track(90, speck), 1080, 30.0)
    # The threshold is a share of the frame, so it scales with resolution.
    at_1080p = (100.0, 100.0, 300.0, 170.0)  # 70 px tall
    assert is_countable(track(90, at_1080p), 1080, 30.0)
    assert not is_countable(track(90, at_1080p), 1440, 30.0)


def test_one_close_frame_is_enough_for_the_size_rule():
    observations = track(60, (100.0, 100.0, 140.0, 130.0)) + [(60, (100.0, 100.0, 400.0, 400.0))]
    assert is_countable(observations, 1080, 30.0)


def test_no_observations_never_count():
    assert not is_countable([], 1080, 30.0)
    assert not is_camera_car([], 1920, 1080, 30.0)


def test_rules_can_be_changed():
    assert is_countable(track(10, (0.0, 0.0, 300.0, 400.0)), 1080, 30.0, TrackRules(min_seconds=0.2))


# --- the camera car's own bonnet ---------------------------------------------------------------


def test_bodywork_resting_on_the_bottom_edge_for_the_whole_clip_is_the_camera_car():
    bonnet = (300.0, 800.0, 1700.0, 1080.0)
    assert is_camera_car(track(3600, bonnet), 1920, 1080, 30.0)


def test_a_vehicle_that_touches_the_bottom_edge_briefly_is_not_the_camera_car():
    close_car = (600.0, 500.0, 1500.0, 1080.0)
    assert not is_camera_car(track(60, close_car), 1920, 1080, 30.0)  # two seconds


def test_a_long_lived_vehicle_ahead_that_is_not_on_the_bottom_edge_is_not_the_camera_car():
    car_ahead = (700.0, 500.0, 1200.0, 800.0)
    assert not is_camera_car(track(3600, car_ahead), 1920, 1080, 30.0)


def test_something_narrow_at_the_bottom_is_not_the_camera_car():
    wiper = (900.0, 900.0, 1000.0, 1080.0)
    assert not is_camera_car(track(3600, wiper), 1920, 1080, 30.0)


def test_mostly_on_the_bottom_edge_is_enough():
    bonnet = track(900, (300.0, 800.0, 1700.0, 1080.0))
    lifted = track(100, (300.0, 780.0, 1700.0, 1060.0), start=900)  # detector drew it slightly short
    assert is_camera_car(bonnet + lifted, 1920, 1080, 30.0)


# --- the camera car's cabin, seen from inside ----------------------------------------------------

# From truck_part02: the cab's door pillar, window and mirror boxed as a "car" for 39 seconds,
# with the vehicles on the road seen through it.
CABIN = (570.0, 0.0, 1470.0, 920.0)  # 47% of a 1920-wide frame
CAR_THROUGH_WINDOW = (1250.0, 180.0, 1400.0, 300.0)
CAR_BESIDE = (1300.0, 400.0, 1700.0, 700.0)  # sticks out past the cabin box
BUS_AHEAD = (500.0, 150.0, 1400.0, 900.0)  # as wide as the cabin, but nothing is wholly inside it


def others(*boxes):
    return lambda frame: list(boxes)


def test_a_very_wide_track_with_other_vehicles_seen_through_it_is_the_camera_car():
    assert is_camera_car(track(150, CABIN), 1920, 1080, 30.0, others_in_frame=others(CAR_THROUGH_WINDOW))


def test_the_cabin_only_needs_other_vehicles_inside_it_some_of_the_time():
    def sometimes(frame):
        return [CAR_THROUGH_WINDOW] if frame % 5 == 0 else []  # one frame in five

    assert is_camera_car(track(150, CABIN), 1920, 1080, 30.0, others_in_frame=sometimes)


def test_a_wide_vehicle_ahead_with_nothing_wholly_inside_it_is_not_the_camera_car():
    assert not is_camera_car(track(150, BUS_AHEAD), 1920, 1080, 30.0, others_in_frame=others(CAR_BESIDE))


def test_a_vehicle_narrower_than_two_fifths_of_the_frame_is_not_the_cabin():
    van = (700.0, 300.0, 1300.0, 800.0)  # 31% wide, with a motorcycle wholly in front of it
    motorcycle = (900.0, 500.0, 1000.0, 750.0)
    assert not is_camera_car(track(150, van), 1920, 1080, 30.0, others_in_frame=others(motorcycle))


def test_the_cabin_must_be_in_view_for_a_few_seconds():
    assert not is_camera_car(track(60, CABIN), 1920, 1080, 30.0, others_in_frame=others(CAR_THROUGH_WINDOW))


def test_without_the_other_boxes_only_the_bonnet_shape_is_checked():
    assert not is_camera_car(track(150, CABIN), 1920, 1080, 30.0)
