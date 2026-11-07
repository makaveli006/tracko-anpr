"""Number plate detection inside vehicle crops.

The detector is a YOLO26s chosen by comparison on this project's own footage
(tools/plate_detector_eval/RESULTS.md). It came from a third-party `.pt` file, which
can run code when loaded, so the application never loads that file. Instead it uses
a copy re-saved inside a sandbox as plain data:

    <name>.safetensors   the network's numbers
    <name>.yaml          the network's layout
    <name>.json          where it came from and its class names

The network is rebuilt here from the layout with the installed Ultralytics code,
and the numbers are loaded into it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tracko_anpr.pipeline.cropping import Box, Crop, crop_region

DEFAULT_IMAGE_SIZE = 640
DEFAULT_CONFIDENCE = 0.25

# Margin kept around a plate box when it is cut out for reading, as a fraction of the box.
PLATE_PAD_X = 0.05
PLATE_PAD_Y = 0.08
# Anything smaller than this cannot hold readable characters.
MIN_PLATE_WIDTH = 16
MIN_PLATE_HEIGHT = 8


@dataclass(frozen=True)
class PlateBox:
    """A number plate found in an image. The box is in that image's own pixels."""

    box: Box
    confidence: float

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]


def model_files(weights: str | Path) -> tuple[Path, Path, Path]:
    """The three files that make up a safely saved model: numbers, layout, details."""
    weights = Path(weights)
    if weights.suffix != ".safetensors":
        raise ValueError(
            f"Refusing to load {weights.name}: only a model re-saved as .safetensors is accepted. "
            "A .pt file can run code when loaded; see tools/plate_detector_eval/README.md."
        )
    layout, details = weights.with_suffix(".yaml"), weights.with_suffix(".json")
    for path in (weights, layout, details):
        if not path.is_file():
            raise FileNotFoundError(f"Plate detector file not found: {path}. See 'Model Files' in ARCHITECTURE.md.")
    return weights, layout, details


def cut_plate(image: np.ndarray, plate: PlateBox) -> Crop | None:
    """Cut a found plate out of the image it was found in, with a small margin, for the reader.

    Returns None when the plate is too small to hold readable characters.
    """
    crop = crop_region(image, plate.box, PLATE_PAD_X, PLATE_PAD_Y)
    if crop is None or crop.width < MIN_PLATE_WIDTH or crop.height < MIN_PLATE_HEIGHT:
        return None
    return crop


class PlateDetector:
    """Finds number plates in vehicle crops."""

    def __init__(
        self,
        weights: str | Path,
        image_size: int = DEFAULT_IMAGE_SIZE,
        confidence: float = DEFAULT_CONFIDENCE,
    ) -> None:
        weights_path, layout_path, details_path = model_files(weights)

        # Imported here so that the rest of the package (and its tests) loads without PyTorch.
        import torch
        from safetensors.torch import load_file
        from ultralytics.models.yolo.detect import DetectionPredictor
        from ultralytics.nn.tasks import DetectionModel
        from ultralytics.utils import YAML

        self.details = json.loads(details_path.read_text(encoding="utf-8"))
        names = {int(key): value for key, value in self.details["class_names"].items()}

        # The layout is passed as a dictionary, not a path: given a path, Ultralytics guesses the
        # model's size from the file name and can silently build a network of the wrong size.
        layout = YAML.load(layout_path)
        if not layout.get("scale"):
            raise ValueError(f"{layout_path.name} does not say which model size it is (no 'scale').")
        network = DetectionModel(cfg=layout, ch=3, nc=len(names), verbose=False)
        network.load_state_dict(load_file(str(weights_path)), strict=True)
        network.names = names
        network.eval()

        self._torch = torch
        self.on_gpu = torch.cuda.is_available()
        self.image_size = image_size
        self.confidence = confidence
        options = {
            "task": "detect",
            "mode": "predict",
            "imgsz": image_size,
            "conf": confidence,
            "device": 0 if self.on_gpu else "cpu",
            "max_det": 10,
            "save": False,
            "verbose": False,
        }
        if self.on_gpu:
            options["quantize"] = 16  # FP16 where supported
        self._predictor = DetectionPredictor(overrides=options)
        self._predictor.setup_model(model=network, verbose=False)

    @property
    def precision(self) -> str:
        return "FP16" if self.on_gpu else "FP32"

    def detect(self, images: list[np.ndarray], batch_size: int = 32) -> list[list[PlateBox]]:
        """Plates found in each image, most confident first. An image with none gives an empty list."""
        found: list[list[PlateBox]] = []
        for start in range(0, len(images), batch_size):
            results = self._predictor(source=images[start : start + batch_size], stream=False)
            for result in results:
                boxes = result.boxes
                plates = []
                if boxes is not None and len(boxes):
                    for box, confidence in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), strict=True):
                        plates.append(PlateBox(tuple(box), float(confidence)))
                found.append(sorted(plates, key=lambda plate: -plate.confidence))
        return found
