"""Tests for the reader's own logic. None of them loads the model or needs the GPU."""

from pathlib import Path

import numpy as np
import pytest
from anpr_ocr.cli import collect_images, describe
from anpr_ocr.recognizer import (
    INPUT_HEIGHT,
    INPUT_MAX_WIDTH,
    PLATE_WIDTH_GAIN,
    Locations,
    Reading,
    is_abstention,
    is_readable_image,
    make_reading,
    preprocess,
    resize_for_recognition,
)


def image(height: int, width: int, value: int = 255) -> np.ndarray:
    return np.full((height, width, 3), value, dtype=np.uint8)


# --- fitting a crop into the model's input ---------------------------------------------------------


@pytest.mark.parametrize(("height", "width"), [(24, 80), (48, 100), (100, 300), (30, 30)])
def test_crops_are_widened_and_padded_with_black(height, width):
    resized = resize_for_recognition(image(height, width))
    assert resized.shape == (INPUT_HEIGHT, INPUT_MAX_WIDTH, 3)
    expected_width = int(width * INPUT_HEIGHT / height * PLATE_WIDTH_GAIN)
    assert resized[:, :expected_width].min() == 255  # the plate itself
    assert resized[:, expected_width:].max() == 0  # padding to the right


def test_widening_can_be_turned_off():
    resized = resize_for_recognition(image(48, 100), gain=1.0)
    assert resized[:, :100].min() == 255
    assert resized[:, 100:].max() == 0


def test_very_wide_crops_are_squeezed_to_the_maximum_width():
    resized = resize_for_recognition(image(20, 400))
    assert resized.shape == (INPUT_HEIGHT, INPUT_MAX_WIDTH, 3)
    assert resized.min() == 255  # no padding left


def test_preprocess_gives_channels_first_values_from_minus_one_to_one():
    tensor = preprocess(image(48, 100))
    assert tensor.shape == (3, INPUT_HEIGHT, INPUT_MAX_WIDTH)
    assert tensor.dtype == np.float32
    assert tensor[:, :, :150].min() == pytest.approx(1.0)  # white plate, widened to 150
    assert tensor[:, :, 150:].max() == pytest.approx(-1.0)  # black padding


def test_unreadable_images_are_recognised_as_such():
    assert is_readable_image(image(10, 10))
    assert not is_readable_image(None)
    assert not is_readable_image(np.zeros((0, 10, 3), dtype=np.uint8))
    assert not is_readable_image(np.zeros((10, 10), dtype=np.uint8))


# --- the model's "cannot read this" answer ---------------------------------------------------------


@pytest.mark.parametrize("text", ["UNREADBLE", "UNREADABLE", "UNREADLE", "UNRREAADLE", "UNREDBLE", "unreadble"])
def test_the_abstention_word_and_its_garbled_forms_are_recognised(text):
    assert is_abstention(text)


@pytest.mark.parametrize("text", ["KL07CN9092", "KL57B1883", "22BH1234AA", "UP14BQ9208", "", "KA", "UN12"])
def test_real_plates_are_never_taken_for_the_abstention_word(text):
    assert not is_abstention(text)


def test_an_abstention_becomes_an_empty_unreadable_reading():
    reading = make_reading("UNREADBLE", 0.86, "UNREDBLE")
    assert reading == Reading("", 0.86, unreadable=True, ctc_text="")
    assert not reading.decoders_agree
    assert describe(reading) == "(unreadable)"


def test_readings_are_tidied_and_the_second_opinion_is_kept():
    reading = make_reading(" kl57b1883 ", 0.91, "KL57B883")
    assert (reading.text, reading.confidence, reading.unreadable, reading.ctc_text) == (
        "KL57B1883",
        0.91,
        False,
        "KL57B883",
    )
    assert not reading.decoders_agree
    assert make_reading("KL07CN9092", 0.92, "KL07CN9092").decoders_agree
    assert describe(Reading("", 0.0)) == "(nothing read)"


# --- files ----------------------------------------------------------------------------------------


def test_collect_images_takes_one_file_or_a_folder_in_name_order(tmp_path: Path):
    for name in ("b.jpg", "a.png", "notes.txt", "c.JPG"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    assert [p.name for p in collect_images(tmp_path)] == ["a.png", "b.jpg", "c.JPG"]
    assert collect_images(tmp_path / "a.png") == [tmp_path / "a.png"]
    with pytest.raises(FileNotFoundError):
        collect_images(tmp_path / "absent")


def test_default_locations_follow_the_repository_layout():
    locations = Locations.default()
    assert locations.model.parts[-3:] == ("models", "awiros", "model.safetensors")
    assert locations.dictionary.name == "en_dict.txt"
    assert locations.paddleocr.parts[-3:] == ("ocr", "vendor", "PaddleOCR")


def test_missing_files_are_reported_by_name(tmp_path: Path):
    locations = Locations(model=tmp_path / "m.safetensors", dictionary=tmp_path / "d.txt", paddleocr=tmp_path)
    with pytest.raises(FileNotFoundError, match="PaddleOCR source not found"):
        locations.check()
    (tmp_path / "ppocr").mkdir()
    (tmp_path / "ppocr" / "__init__.py").write_text("")
    with pytest.raises(FileNotFoundError, match="OCR model not found"):
        locations.check()
