import numpy as np
import pytest

from tracko_anpr.pipeline.cropping import best_frames, box_area, box_inside, crop_region


def numbered_frame(height: int, width: int) -> np.ndarray:
    """A frame in which every pixel's value encodes its own position, so crops can be checked exactly."""
    rows, columns = np.indices((height, width))
    return np.stack([rows % 256, columns % 256, (rows + columns) % 256], axis=2).astype(np.uint8)


@pytest.mark.parametrize(("height", "width"), [(1080, 1920), (1440, 2560)])
def test_crop_has_exactly_the_boxes_size_and_pixels_at_any_resolution(height, width):
    frame = numbered_frame(height, width)
    crop = crop_region(frame, (100.0, 200.0, 612.0, 584.0))
    assert (crop.width, crop.height) == (512, 384)
    assert crop.image.shape == (384, 512, 3)
    assert np.array_equal(crop.image, frame[200:584, 100:612])  # the original pixels, not a resized copy


def test_fractional_boxes_grow_outwards_so_nothing_of_the_vehicle_is_lost():
    crop = crop_region(numbered_frame(100, 100), (10.4, 20.6, 30.2, 40.1))
    assert (crop.x1, crop.y1, crop.x2, crop.y2) == (10, 20, 31, 41)


def test_padding_is_a_fraction_of_the_box_and_stops_at_the_frame_edge():
    frame = numbered_frame(100, 200)
    padded = crop_region(frame, (50.0, 40.0, 150.0, 60.0), pad_x=0.1, pad_y=0.5)
    assert (padded.x1, padded.y1, padded.x2, padded.y2) == (40, 30, 160, 70)
    clamped = crop_region(frame, (0.0, 0.0, 200.0, 100.0), pad_x=0.5, pad_y=0.5)
    assert (clamped.x1, clamped.y1, clamped.x2, clamped.y2) == (0, 0, 200, 100)


def test_a_box_outside_the_frame_gives_no_crop():
    assert crop_region(numbered_frame(50, 50), (60.0, 60.0, 80.0, 80.0)) is None
    assert crop_region(numbered_frame(50, 50), (10.0, 10.0, 10.0, 30.0)) is None


def test_a_crop_is_a_copy_so_drawing_on_it_leaves_the_frame_alone():
    frame = numbered_frame(50, 50)
    crop = crop_region(frame, (5.0, 5.0, 25.0, 25.0))
    crop.image[:] = 0
    assert frame[10, 10].any()


def test_boxes_found_inside_a_crop_map_back_to_frame_coordinates():
    crop = crop_region(numbered_frame(400, 600), (100.0, 50.0, 300.0, 250.0))
    assert crop.to_frame((10.0, 20.0, 60.0, 40.0)) == (110.0, 70.0, 160.0, 90.0)


def test_box_helpers():
    assert box_area((0.0, 0.0, 10.0, 5.0)) == 50.0
    assert box_area((10.0, 0.0, 5.0, 5.0)) == 0.0
    assert box_inside((10.0, 10.0, 90.0, 90.0), 100, 100)
    assert not box_inside((0.0, 10.0, 90.0, 90.0), 100, 100)  # touches the left edge
    assert not box_inside((10.0, 10.0, 99.5, 90.0), 100, 100)  # touches the right edge


def test_best_frames_prefers_the_largest_box_that_is_not_cut_off():
    observations = [
        (0, (10.0, 10.0, 60.0, 60.0)),  # small
        (20, (10.0, 10.0, 200.0, 200.0)),  # large and whole
        (40, (0.0, 0.0, 400.0, 400.0)),  # largest, but cut off by the frame edge
    ]
    assert best_frames(observations, 500, 500, count=2) == [20, 0]


def test_best_frames_keeps_its_choices_apart():
    observations = [(index, (10.0, 10.0, 100.0 + index, 100.0 + index)) for index in range(30)]
    assert best_frames(observations, 500, 500, count=3, min_gap=8) == [29, 21, 13]


def test_best_frames_falls_back_to_cut_off_frames_when_there_is_nothing_else():
    observations = [(5, (0.0, 0.0, 50.0, 50.0)), (25, (0.0, 0.0, 80.0, 80.0))]
    assert best_frames(observations, 500, 500, count=1) == [25]
    assert best_frames([], 500, 500) == []
