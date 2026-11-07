"""Load the Awiros-ANPR-OCR model and read number plate crops.

The network is built from PaddleOCR's source code (the vendored `ppocr` package),
configured as Awiros's own `test.py` configures it, and the published weights are
loaded into it.

Two things here differ from that reference script, both found by testing on
Awiros's own sample plates and on plates cut from this project's clips
(see "OCR Smoke Test" in ARCHITECTURE.md):

1. **The attention decoder is used, not the CTC one.** The model has two decoders.
   The reference script reads the CTC head, which drops a character on almost every
   two-line plate. The attention ("NRTR") head writes the text one character at a
   time and reads two-line plates correctly.
2. **The plate is drawn 1.5 times wider** before it goes into the model. At its
   natural shape, characters near the right edge are sometimes lost.

The CTC reading is still returned beside the main one, as a second opinion.
"""

from __future__ import annotations

import contextlib
import difflib
import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

INPUT_HEIGHT = 48
INPUT_MAX_WIDTH = 320
PLATE_WIDTH_GAIN = 1.5

# The model was trained to answer with this word (spelled this way) when a plate cannot be read.
ABSTENTION_WORD = "UNREADBLE"

# From Awiros's test.py: PP-OCRv5 server recognition model (SVTR_HGNet).
# The CTC head outputs 64 classes (63 dictionary characters + blank); the NRTR head is
# declared as 67 because PaddleOCR adds one internally, giving the 68 the weights expect.
ARCHITECTURE = {
    "model_type": "rec",
    "algorithm": "SVTR_HGNet",
    "Transform": None,
    "Backbone": {"name": "PPHGNetV2_B4", "text_rec": True},
    "Head": {
        "name": "MultiHead",
        "out_channels_list": {"CTCLabelDecode": 64, "NRTRLabelDecode": 67},
        "head_list": [
            {
                "CTCHead": {
                    "Neck": {
                        "name": "svtr",
                        "dims": 120,
                        "depth": 2,
                        "hidden_dims": 120,
                        "kernel_size": [1, 3],
                        "use_guide": True,
                    },
                    "Head": {"fc_decay": 1e-05},
                }
            },
            {"NRTRHead": {"nrtr_dim": 384, "max_text_length": 25}},
        ],
    },
}


@dataclass(frozen=True)
class Reading:
    """What the model read on one plate crop."""

    text: str
    """The plate text from the attention decoder, upper case. Empty when nothing could be read."""
    confidence: float
    """How sure the model is, 0 to 1. Not a measure of whether the reading is right."""
    unreadable: bool = False
    """True when the model itself answered that the plate cannot be read."""
    ctc_text: str = ""
    """The CTC decoder's reading of the same crop: a second opinion, weaker on two-line plates."""

    @property
    def decoders_agree(self) -> bool:
        return bool(self.text) and self.text == self.ctc_text


NOTHING_READ = Reading("", 0.0)


@dataclass(frozen=True)
class Locations:
    """Where the files the recognizer needs live. Defaults follow the repository layout."""

    model: Path
    dictionary: Path
    paddleocr: Path

    @classmethod
    def default(cls) -> Locations:
        ocr_dir = Path(__file__).resolve().parents[2]
        models = ocr_dir.parent / "models" / "awiros"
        return cls(
            model=Path(os.environ.get("ANPR_OCR_MODEL", models / "model.safetensors")),
            dictionary=Path(os.environ.get("ANPR_OCR_DICTIONARY", models / "en_dict.txt")),
            paddleocr=Path(os.environ.get("ANPR_OCR_PADDLEOCR", ocr_dir / "vendor" / "PaddleOCR")),
        )

    def check(self) -> None:
        """Raise a clear error naming whichever file is missing."""
        if not (self.paddleocr / "ppocr" / "__init__.py").is_file():
            raise FileNotFoundError(f"PaddleOCR source not found at {self.paddleocr}. See ocr/README.md.")
        for label, path in (("OCR model", self.model), ("character dictionary", self.dictionary)):
            if not path.is_file():
                raise FileNotFoundError(f"{label} not found at {path}. See ocr/README.md.")


def resize_for_recognition(image: np.ndarray, gain: float = PLATE_WIDTH_GAIN) -> np.ndarray:
    """Scale a plate crop to the model's height, widen it by `gain`, and pad the right side with black.

    A crop that would come out wider than the model allows is squeezed to the maximum width.
    """
    height, width = image.shape[:2]
    new_width = max(1, min(int(width * INPUT_HEIGHT / height * gain), INPUT_MAX_WIDTH))
    resized = cv2.resize(image, (new_width, INPUT_HEIGHT))
    if new_width == INPUT_MAX_WIDTH:
        return resized
    padded = np.zeros((INPUT_HEIGHT, INPUT_MAX_WIDTH, 3), dtype=np.uint8)
    padded[:, :new_width] = resized
    return padded


def preprocess(image: np.ndarray) -> np.ndarray:
    """BGR plate crop to the model's input: 3 x 48 x 320, values from -1 to 1."""
    resized = resize_for_recognition(image).astype(np.float32) / 255.0
    return ((resized - 0.5) / 0.5).transpose((2, 0, 1))


def is_readable_image(image: np.ndarray | None) -> bool:
    return image is not None and image.ndim == 3 and image.shape[0] > 0 and image.shape[1] > 0


def is_abstention(text: str) -> bool:
    """True when the text is the model's "cannot read this" answer, or a garbled form of it.

    A real Indian plate always contains digits; the abstention word never does.
    """
    letters = "".join(character for character in text.upper() if character.isalpha())
    if not letters or any(character.isdigit() for character in text):
        return False
    return difflib.SequenceMatcher(None, letters, ABSTENTION_WORD).ratio() >= 0.7


def make_reading(text: str, confidence: float, ctc_text: str) -> Reading:
    """Tidy the decoders' raw output into a Reading."""
    text = text.strip().upper()
    ctc_text = ctc_text.strip().upper()
    if is_abstention(text):
        return Reading("", float(confidence), unreadable=True, ctc_text="" if is_abstention(ctc_text) else ctc_text)
    return Reading(text, float(confidence), ctc_text="" if is_abstention(ctc_text) else ctc_text)


class PlateRecognizer:
    """Reads number plate crops. Loading takes a few seconds; reading is fast, so keep one instance alive."""

    def __init__(self, locations: Locations | None = None, device: str = "auto") -> None:
        self.locations = locations or Locations.default()
        self.locations.check()

        # PaddleOCR prints to standard output while importing, and its source triggers SyntaxWarnings.
        # Keep both off standard output, which is reserved for this program's own results.
        sys.path.insert(0, str(self.locations.paddleocr))
        with warnings.catch_warnings(), contextlib.redirect_stdout(sys.stderr):
            warnings.simplefilter("ignore", SyntaxWarning)
            import paddle
            from ppocr.modeling.architectures import build_model
            from ppocr.postprocess import build_post_process
            from safetensors.numpy import load_file

        self._paddle = paddle
        if device == "auto":
            device = "gpu" if paddle.is_compiled_with_cuda() else "cpu"
        paddle.set_device(device)
        self.device = paddle.device.get_device()

        decoder_options = {"character_dict_path": str(self.locations.dictionary), "use_space_char": True}
        self._decode_attention = build_post_process({"name": "NRTRLabelDecode", **decoder_options})
        self._decode_ctc = build_post_process({"name": "CTCLabelDecode", **decoder_options})

        self._model = build_model(ARCHITECTURE)
        self._model.eval()
        weights = load_file(str(self.locations.model))
        self._model.set_state_dict({name: paddle.to_tensor(value) for name, value in weights.items()})

    def read(self, images: list[np.ndarray | None], batch_size: int = 32) -> list[Reading]:
        """Read each crop. An empty or missing image gives an empty reading with confidence 0."""
        readings = [NOTHING_READ] * len(images)
        usable = [index for index, image in enumerate(images) if is_readable_image(image)]
        head = self._model.head

        for start in range(0, len(usable), batch_size):
            indexes = usable[start : start + batch_size]
            batch = self._paddle.to_tensor(np.stack([preprocess(images[index]) for index in indexes]))
            with self._paddle.no_grad():
                features = self._model.backbone(batch)
                # The model's own forward pass only returns the CTC branch outside training,
                # so both decoders are run on the shared features here.
                attention = head.gtc_head(head.before_gtc(features))
                ctc = head.ctc_head(head.ctc_encoder(features))

            attention_texts = self._decode_attention([part.numpy() for part in attention])
            ctc_texts = self._decode_ctc(ctc.numpy())
            for index, (text, confidence), (ctc_text, _) in zip(indexes, attention_texts, ctc_texts, strict=True):
                readings[index] = make_reading(text, confidence, ctc_text)
        return readings
