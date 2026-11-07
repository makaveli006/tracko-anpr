"""Tests for plate handling that need no model: file checks and cutting a found plate out."""

from pathlib import Path

import numpy as np
import pytest

from tracko_anpr.config import load_settings
from tracko_anpr.pipeline.plates import MIN_PLATE_HEIGHT, MIN_PLATE_WIDTH, PlateBox, cut_plate, model_files


def test_a_pt_file_is_refused_outright(tmp_path: Path):
    unsafe = tmp_path / "best.pt"
    unsafe.write_bytes(b"anything")
    with pytest.raises(ValueError, match="only a model re-saved as .safetensors"):
        model_files(unsafe)


@pytest.mark.parametrize("missing", ["model.safetensors", "model.yaml", "model.json"])
def test_each_of_the_three_model_files_must_exist(tmp_path: Path, missing):
    for name in ("model.safetensors", "model.yaml", "model.json"):
        if name != missing:
            (tmp_path / name).write_bytes(b"x")
    with pytest.raises(FileNotFoundError, match=missing):
        model_files(tmp_path / "model.safetensors")


def test_the_three_files_sit_side_by_side(tmp_path: Path):
    for name in ("model.safetensors", "model.yaml", "model.json"):
        (tmp_path / name).write_bytes(b"x")
    weights, layout, details = model_files(tmp_path / "model.safetensors")
    assert (weights.name, layout.name, details.name) == ("model.safetensors", "model.yaml", "model.json")


def test_default_plate_model_is_the_safely_saved_one(tmp_path: Path):
    settings = load_settings(root=tmp_path, environ={})
    assert settings.plate_weights == tmp_path / "models" / "plate" / "sentry-26s.safetensors"
    assert settings.plate_weights.suffix == ".safetensors"
    assert (settings.plate_image_size, settings.plate_confidence) == (640, 0.25)


def test_plate_box_size():
    plate = PlateBox((10.0, 20.0, 110.0, 50.0), 0.9)
    assert (plate.width, plate.height) == (100.0, 30.0)


def test_a_plate_is_cut_out_with_a_margin_from_the_original_pixels():
    rows, columns = np.indices((200, 300))
    image = np.stack([rows % 256, columns % 256, (rows + columns) % 256], axis=2).astype(np.uint8)
    crop = cut_plate(image, PlateBox((100.0, 80.0, 200.0, 105.0), 0.8))
    # 5% of the width each side, 8% of the height top and bottom
    assert (crop.x1, crop.y1, crop.x2, crop.y2) == (95, 78, 205, 107)
    assert np.array_equal(crop.image, image[78:107, 95:205])


def test_plates_too_small_to_read_are_dropped():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    assert cut_plate(image, PlateBox((10.0, 10.0, 10.0 + MIN_PLATE_WIDTH - 6, 30.0), 0.9)) is None
    assert cut_plate(image, PlateBox((10.0, 10.0, 60.0, 10.0 + MIN_PLATE_HEIGHT - 4), 0.9)) is None
    assert cut_plate(image, PlateBox((10.0, 10.0, 60.0, 30.0), 0.9)) is not None
