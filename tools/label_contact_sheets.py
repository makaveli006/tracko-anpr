"""Blind contact sheets for hand labelling: crops only, so the labeller cannot see what the system read.

The accuracy procedure in ARCHITECTURE.md ("HOW TO MEASURE REAL ACCURACY") forbids looking at the
system's number before writing the true one. This takes only the `track` column of an exported
CSV and draws, for each track, its vehicle crop and its plate crops, enlarged, captioned with the
track and frame. It never reads or prints a number or a status.

    uv run python tools/label_contact_sheets.py labels/zoomed-in_system.csv zoomed-in <output folder>
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TILE_WIDTH, TILE_HEIGHT = 300, 150
VEHICLE_SIZE = 300
PLATES_PER_TRACK = 6
TRACKS_PER_SHEET = 4
BACKGROUND = (24, 24, 24)
CAPTION = (255, 255, 255)


def fit(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """The image scaled to fit the box, enlarged if small, centred on the background."""
    scale = min(width / image.shape[1], height / image.shape[0])
    size = (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale)))
    resized = cv2.resize(image, size, interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
    tile = np.full((height, width, 3), BACKGROUND, dtype=np.uint8)
    top, left = (height - size[1]) // 2, (width - size[0]) // 2
    tile[top : top + size[1], left : left + size[0]] = resized
    return tile


def caption(tile: np.ndarray, text: str) -> None:
    cv2.rectangle(tile, (0, 0), (8 + 9 * len(text), 18), BACKGROUND, cv2.FILLED)
    cv2.putText(tile, text, (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, CAPTION, 1, cv2.LINE_AA)


def plate_crops(folder: Path, track: str) -> list[Path]:
    """A track's plate crops, spread evenly when there are more than fit."""
    found = sorted(folder.glob(f"{track}_f*.png"))
    if len(found) <= PLATES_PER_TRACK:
        return found
    step = (len(found) - 1) / (PLATES_PER_TRACK - 1)
    return [found[round(index * step)] for index in range(PLATES_PER_TRACK)]


def track_row(video: str, track: str) -> np.ndarray:
    """One track: the vehicle on the left, up to six plates in two rows of three."""
    row = np.full((VEHICLE_SIZE, VEHICLE_SIZE + 3 * TILE_WIDTH, 3), BACKGROUND, dtype=np.uint8)
    vehicle = cv2.imread(str(ROOT / "storage" / "vehicle_crops" / video / f"{track}.jpg"))
    tile = fit(vehicle, VEHICLE_SIZE, VEHICLE_SIZE) if vehicle is not None else row[:, :VEHICLE_SIZE].copy()
    caption(tile, track)
    row[:, :VEHICLE_SIZE] = tile
    for position, path in enumerate(plate_crops(ROOT / "storage" / "plate_crops" / video, track)):
        plate = cv2.imread(str(path))
        if plate is None:
            continue
        tile = fit(plate, TILE_WIDTH - 4, TILE_HEIGHT - 4)
        frame = re.search(r"_f0*(\d+)", path.stem)
        caption(tile, f"{track} f{frame.group(1) if frame else '?'} {plate.shape[1]}px")
        top, left = (position // 3) * TILE_HEIGHT, VEHICLE_SIZE + (position % 3) * TILE_WIDTH
        row[top + 2 : top + TILE_HEIGHT - 2, left + 2 : left + TILE_WIDTH - 2] = tile
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="The exported CSV; only its track column is read.")
    parser.add_argument("video", help="The video's name under storage/.")
    parser.add_argument("output", type=Path, help="Where to write the sheets (keep it out of the repo).")
    args = parser.parse_args()

    with args.export.open(encoding="utf-8", newline="") as handle:
        tracks = sorted({row["track"] for row in csv.DictReader(handle)}, key=lambda track: int(track[1:]))
    args.output.mkdir(parents=True, exist_ok=True)
    for number, start in enumerate(range(0, len(tracks), TRACKS_PER_SHEET), 1):
        rows = [track_row(args.video, track) for track in tracks[start : start + TRACKS_PER_SHEET]]
        cv2.imwrite(str(args.output / f"sheet_{number:02d}.png"), np.vstack(rows))
    print(f"{len(tracks)} tracks on {number} sheets in {args.output}")


if __name__ == "__main__":
    main()
