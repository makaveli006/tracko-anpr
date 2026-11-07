"""Write what the tracking pass found to files that later passes and people can read."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from tracko_anpr.pipeline.cropping import Box
from tracko_anpr.pipeline.tracking import TrackingRun, format_track_id
from tracko_anpr.pipeline.video import VideoInfo


def frame_time(frame_index: int, fps: float) -> float:
    """Seconds from the start of the video at which a frame is shown."""
    return frame_index / fps


def format_timestamp(seconds: float) -> str:
    """hh:mm:ss, as shown in the dashboard tables."""
    whole = int(seconds)
    return f"{whole // 3600:02d}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def write_detections_csv(path: str | Path, info: VideoInfo, run: TrackingRun) -> Path:
    """One row per tracked vehicle per frame, with the box in original-frame pixels."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fps = info.fps_float
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["frame", "time_s", "track_id", "class", "confidence", "x1", "y1", "x2", "y2"])
        for frame_index, vehicles in enumerate(run.frames):
            for vehicle in vehicles:
                writer.writerow(
                    [
                        frame_index,
                        f"{frame_time(frame_index, fps):.3f}",
                        vehicle.track_id,
                        vehicle.class_name,
                        f"{vehicle.confidence:.4f}",
                        *(f"{value:.1f}" for value in vehicle.box),
                    ]
                )
    return path


def track_records(info: VideoInfo, run: TrackingRun) -> list[dict]:
    """One summary per track, in order of first appearance, with the direction read from its boxes."""
    from tracko_anpr.pipeline.direction import travel_direction

    fps = info.fps_float
    history: dict[int, list[tuple[int, Box]]] = {}
    for frame_index, tracked in enumerate(run.frames):
        for vehicle in tracked:
            history.setdefault(vehicle.track_id, []).append((frame_index, vehicle.box))
    ordered = sorted(run.registry.tracks.values(), key=lambda track: (track.first_frame, track.track_id))
    return [
        {
            "track_id": track.track_id,
            "label": format_track_id(track.track_id),
            "class": track.class_name,
            "first_frame": track.first_frame,
            "last_frame": track.last_frame,
            "first_seen_s": round(frame_time(track.first_frame, fps), 3),
            "last_seen_s": round(frame_time(track.last_frame, fps), 3),
            "frames_seen": track.frames_seen,
            "best_confidence": round(track.best_confidence, 4),
            "direction": travel_direction(history.get(track.track_id, []), info.width).label,
        }
        for track in ordered
    ]


def write_tracks_json(path: str | Path, info: VideoInfo, run: TrackingRun, extra: dict) -> Path:
    """Video properties, per-track summaries, and whatever run details the caller adds."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "video": {
            "file": info.path.name,
            "width": info.width,
            "height": info.height,
            "fps": str(info.fps),
            "fps_decimal": round(info.fps_float, 4),
            "frame_count": info.frame_count,
            "duration_s": round(info.duration_s, 3),
        },
        "frames_processed": run.frame_count,
        "counts": {"tracks": len(run.registry.tracks), "by_class": run.registry.counts_by_class()},
        **extra,
        "tracks": track_records(info, run),
    }
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path
