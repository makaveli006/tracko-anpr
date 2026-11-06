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
