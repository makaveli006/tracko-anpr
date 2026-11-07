"""Command line entry point: `anpr-ocr <command>`."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def collect_images(path: Path) -> list[Path]:
    """A single image, or every image directly inside a folder, in name order."""
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
    raise FileNotFoundError(f"Not found: {path}")


def describe(reading) -> str:
    """The reading as shown in the terminal."""
    if reading.unreadable:
        return "(unreadable)"
    return reading.text or "(nothing read)"


def _run_read(args: argparse.Namespace) -> int:
    # Imported here so `anpr-ocr --help` does not load PaddlePaddle.
    import cv2

    from anpr_ocr.recognizer import PlateRecognizer

    paths = collect_images(args.path)
    if not paths:
        print(f"No images found in {args.path}", file=sys.stderr)
        return 1

    started = time.perf_counter()
    recognizer = PlateRecognizer()
    loaded = time.perf_counter()
    readings = recognizer.read([cv2.imread(str(path)) for path in paths], batch_size=args.batch_size)
    finished = time.perf_counter()

    width = max(len(path.name) for path in paths)
    print(f"{'image':<{width}}  {'reading':<16}  conf    second decoder")
    for path, reading in zip(paths, readings, strict=True):
        second = "same" if reading.decoders_agree else (reading.ctc_text or "-")
        print(f"{path.name:<{width}}  {describe(reading):<16}  {reading.confidence:.4f}  {second}")

    read_seconds = finished - loaded
    print(
        f"\n{len(paths)} images on {recognizer.device}: model loaded in {loaded - started:.1f} s, "
        f"read in {read_seconds:.2f} s ({1000 * read_seconds / len(paths):.1f} ms per image)",
        file=sys.stderr,
    )

    if args.json is not None:
        records = [
            {
                "image": path.name,
                "text": reading.text,
                "confidence": round(reading.confidence, 4),
                "unreadable": reading.unreadable,
                "ctc_text": reading.ctc_text,
            }
            for path, reading in zip(paths, readings, strict=True)
        ]
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return 0


def _run_serve(args: argparse.Namespace) -> int:
    from anpr_ocr.service import run

    return run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anpr-ocr", description="Read number plate crops with Awiros-ANPR-OCR.")
    commands = parser.add_subparsers(dest="command", required=True)

    read = commands.add_parser("read", help="Read one plate image, or every image in a folder.")
    read.add_argument("path", type=Path, help="An image file or a folder of images.")
    read.add_argument("--json", type=Path, default=None, help="Also write the readings to this JSON file.")
    read.add_argument("--batch-size", type=int, default=32, help="Images per batch (default 32).")
    read.set_defaults(handler=_run_read)

    serve = commands.add_parser(
        "serve", help="Run as a service: load the model once, then answer JSON requests on standard input."
    )
    serve.set_defaults(handler=_run_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except FileNotFoundError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
