"""The Settings page's values: the frozen pipeline settings, shown with any stored changes.

The pipeline's settings are frozen (Phase 7): changing one means every demo video must be
processed again. So this service stores what the page sets in `app_settings` and shows it,
but a stored value is not applied to processing unless `applies_to_processing` says so.
For the POC nothing applies; the Settings page is informative. Each job keeps its own
snapshot of what it actually ran with (`processing_jobs.settings`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from tracko_anpr.config import Settings
from tracko_anpr.db.models import AppSetting
from tracko_anpr.pipeline.rules import TrackRules
from tracko_anpr.pipeline.validation import ValidationRules


@dataclass(frozen=True)
class SettingItem:
    key: str
    group: str
    label: str
    value: object
    default: object
    unit: str
    description: str
    editable: bool
    applies_to_processing: bool
    updated_at: datetime | None


def defaults(settings: Settings) -> list[SettingItem]:
    """Every setting the page shows, with the value the pipeline actually uses."""
    track, validation = TrackRules(), ValidationRules()
    rows = [
        # group, key, label, value, unit, description
        (
            "Model configuration",
            "vehicle_weights",
            "Vehicle detector",
            settings.vehicle_weights.name,
            "",
            "YOLO26m, official Ultralytics weights.",
        ),
        (
            "Model configuration",
            "plate_weights",
            "Plate detector",
            settings.plate_weights.name,
            "",
            "sentry-26s (YOLO26s), re-saved safely.",
        ),
        (
            "Model configuration",
            "ocr_model",
            "Plate reader",
            settings.ocr_model.name,
            "",
            "Awiros-ANPR-OCR, attention decoder.",
        ),
        ("Model configuration", "precision", "Inference precision", "FP16", "", "Half precision on the GPU."),
        (
            "Detection thresholds",
            "vehicle_confidence",
            "Vehicle detection confidence",
            settings.vehicle_confidence,
            "",
            "Boxes below this are dropped before tracking.",
        ),
        (
            "Detection thresholds",
            "plate_confidence",
            "Plate detection confidence",
            settings.plate_confidence,
            "",
            "Plate boxes below this are ignored.",
        ),
        (
            "Recognition thresholds",
            "min_reading_confidence",
            "Reading counts from",
            validation.min_reading_confidence,
            "",
            "Readings below this confidence do not vote.",
        ),
        (
            "Recognition thresholds",
            "confirm_confidence",
            "Confirm needs one reading at",
            validation.confirm_confidence,
            "",
            "At least one agreeing reading this confident.",
        ),
        (
            "Recognition thresholds",
            "min_observations",
            "Agreeing frames to confirm",
            validation.min_observations,
            "frames",
            "",
        ),
        (
            "Recognition thresholds",
            "consensus_share",
            "Share of votes to confirm",
            validation.consensus_share,
            "",
            "Confidence-weighted.",
        ),
        (
            "Tracking configuration",
            "tracker",
            "Tracker",
            "TrackTrack",
            "",
            "Built into Ultralytics; camera motion compensation on.",
        ),
        (
            "Tracking configuration",
            "tracker_lost_seconds",
            "Lost track kept for",
            settings.tracker_lost_seconds,
            "s",
            "Scaled to the video's frame rate.",
        ),
        ("Tracking configuration", "min_track_seconds", "Counts as a vehicle after", track.min_seconds, "s", ""),
        (
            "Tracking configuration",
            "min_height_fraction",
            "...and at least this tall",
            track.min_height_fraction,
            "of frame height",
            "65 px at 1080p.",
        ),
        (
            "Processing resolution",
            "vehicle_image_size",
            "Vehicle detector input",
            settings.vehicle_image_size,
            "px",
            "The longer side; frames are resized for detection only.",
        ),
        ("Processing resolution", "plate_image_size", "Plate detector input", settings.plate_image_size, "px", ""),
        (
            "Processing resolution",
            "plate_frames_per_track",
            "Frames examined per vehicle",
            6,
            "frames",
            "Where the vehicle is largest, at least 0.15 s apart.",
        ),
        (
            "Video output",
            "output_resolution",
            "Annotated video resolution",
            "up to 1080p",
            "",
            "Inputs above 1080p are scaled down for playback; frame rate and frame count kept. "
            "The original video, crops and results are never resized.",
        ),
        ("Video output", "output_codec", "Annotated video codec", "H.264 MP4", "", "Audio copied from the original."),
        (
            "Storage",
            "storage_dir",
            "Storage folder",
            str(settings.storage_dir),
            "",
            "uploads/, processed/, vehicle_crops/, plate_crops/.",
        ),
        (
            "Storage",
            "database",
            "Database",
            _hide_password(settings.database_url),
            "",
            "PostgreSQL 18 in Docker inside WSL.",
        ),
    ]
    return [
        SettingItem(
            key,
            group,
            label,
            value,
            value,
            unit,
            description,
            editable=False,
            applies_to_processing=False,
            updated_at=None,
        )
        for group, key, label, value, unit, description in rows
    ]


def current(session: Session, settings: Settings) -> list[SettingItem]:
    """The defaults, overlaid with whatever the Settings page has stored."""
    stored = {row.key: row for row in session.scalars(select(AppSetting)).all()}
    items = []
    for item in defaults(settings):
        row = stored.get(item.key)
        if row is None:
            items.append(item)
        else:
            items.append(
                SettingItem(
                    item.key,
                    item.group,
                    item.label,
                    row.value,
                    item.default,
                    item.unit,
                    item.description,
                    editable=item.editable,
                    applies_to_processing=item.applies_to_processing,
                    updated_at=row.updated_at,
                )  # fmt: skip
            )
    return items


def update(session: Session, key: str, value: object) -> AppSetting:
    """Store a value from the Settings page. It is shown, but not applied to processing (see the module note)."""
    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    session.flush()
    return row


def _hide_password(url: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(url).render_as_string(hide_password=True)
