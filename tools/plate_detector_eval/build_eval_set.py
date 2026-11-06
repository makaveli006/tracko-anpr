"""Build the vehicle crops the plate detectors are compared on.

For each test clip that has already been through `tracko-anpr track`, this takes the
vehicles that came closest to the camera and saves them, cut from the original frame,
at the two frames where each was largest. Every candidate is then run on the same crops.

Run from the repository root, in the main environment:
    uv run python tools/plate_detector_eval/build_eval_set.py
"""

from __future__ import annotations

import csv
from collections import defaultdict

import cv2

from tracko_anpr.config import get_settings
from tracko_anpr.pipeline.cropping import best_frames, box_area, crop_region

# One 2-minute piece of each of the eight test videos.
CLIPS = {
    "trafiic_part01": "videos/clips/trafiic/trafiic_part01.mp4",
    "mavoor_part02": "videos/clips/mavoor/mavoor_part02.mp4",
    "kozhikode_part03": "videos/clips/kozhikode/kozhikode_part03.mp4",
    "kochi_part02": "videos/clips/kochi/kochi_part02.mp4",
    "kochi-city_part05": "videos/clips/kochi-city/kochi-city_part05.mp4",
    "kozikode-4k_part03": "videos/clips/kozikode-4k/kozikode-4k_part03.mp4",
    "ooty_part03": "videos/clips/ooty/ooty_part03.mp4",
    "truck_part02": "videos/clips/truck/truck_part02.mp4",
}
TRACKS_PER_CLIP = 60
FRAMES_PER_TRACK = 2
MIN_VEHICLE_HEIGHT = 110  # pixels; smaller vehicles are too far away for their plate to be read
VEHICLE_PADDING = 0.04


def main() -> None:
    settings = get_settings()
    out = settings.vehicle_crops_dir / "phase4_eval"
    out.mkdir(parents=True, exist_ok=True)
    rows = []

    for clip, video in CLIPS.items():
        detections = settings.processed_dir / f"{clip}_detections.csv"
        if not detections.is_file():
            print(f"{clip}: no detections file, run `tracko-anpr track {video} --no-video` first")
            continue

        tracks = defaultdict(list)
        classes = {}
        with detections.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                box = tuple(float(row[key]) for key in ("x1", "y1", "x2", "y2"))
                tracks[int(row["track_id"])].append((int(row["frame"]), box))
                classes[int(row["track_id"])] = row["class"]

        capture = cv2.VideoCapture(str(settings.root / video))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

        ranked = []
        for track_id, observations in tracks.items():
            boxes = dict(observations)
            chosen = best_frames(observations, width, height, count=FRAMES_PER_TRACK)
            if not chosen or boxes[chosen[0]][3] - boxes[chosen[0]][1] < MIN_VEHICLE_HEIGHT:
                continue
            ranked.append((box_area(boxes[chosen[0]]), track_id, [(frame, boxes[frame]) for frame in chosen]))
        ranked.sort(reverse=True)

        wanted = defaultdict(list)
        for _, track_id, picks in ranked[:TRACKS_PER_CLIP]:
            for frame_index, box in picks:
                wanted[frame_index].append((track_id, box))

        saved = 0
        frame_index, last = 0, max(wanted, default=-1)
        while frame_index <= last and capture.grab():
            if frame_index in wanted:
                ok, frame = capture.retrieve()
                for track_id, box in wanted[frame_index] if ok else []:
                    crop = crop_region(frame, box, VEHICLE_PADDING, VEHICLE_PADDING)
                    if crop is None:
                        continue
                    name = f"{clip}__T{track_id}__f{frame_index:05d}.png"
                    cv2.imwrite(str(out / name), crop.image)
                    rows.append(
                        [name, clip, track_id, frame_index, classes[track_id], crop.width, crop.height, width, height]
                    )
                    saved += 1
            frame_index += 1
        capture.release()
        print(f"{clip}: {len(tracks)} tracks, {min(len(ranked), TRACKS_PER_CLIP)} near enough, {saved} vehicle crops")

    with (out / "index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["file", "clip", "track_id", "frame", "vehicle_class", "width", "height", "frame_width", "frame_height"]
        )
        writer.writerows(rows)
    vehicles = len({(row[1], row[2]) for row in rows})
    print(f"total: {len(rows)} crops of {vehicles} vehicles from {len({row[1] for row in rows})} clips -> {out}")


if __name__ == "__main__":
    main()
