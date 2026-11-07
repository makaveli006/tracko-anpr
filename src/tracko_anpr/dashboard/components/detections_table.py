"""A table of detections (DESIGN sections 12 and 15), shared by the Overview, Video Analysis and History."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from tracko_anpr.dashboard.components.detection_dialog import image_url, status_badge
from tracko_anpr.dashboard.format import VEHICLE_ICONS, video_time
from tracko_anpr.services.results import DetectionRow

COLUMNS = {
    "time": "Time (hh:mm:ss)",
    "video": "Video",
    "track": "Track ID",
    "vehicle_type": "Vehicle",
    "direction": "Direction",
    "registration_number": "Registration Number",
    "confidence": "Confidence",
    "status": "Validation",
    "registry": "Demo Registry",
    "plate": "Plate Image",
}


def corrected_value(shown: str, original: str, by: str) -> ui.element:
    """A value an operator corrected: amber pencil, dashed underline, the system's value in the tooltip."""
    with ui.row().classes("items-center gap-1 no-wrap tk-corrected") as holder:
        ui.icon("edit").classes("text-sm tk-amber")
        ui.label(shown)
        ui.tooltip(
            f"Corrected from {original}" + (f" by {by}" if by else "") + ". The figures use the system's result."
        )
    return holder


DIRECTION_ICONS = {"towards": "arrow_downward", "away": "arrow_upward"}
"""Towards the camera is down the picture, away from it is up; sideways-only travel gets a horizontal arrow."""


def direction_cell(approach: str | None, sideways: str | None, text: str) -> None:
    """The travel direction as a small arrow and the short words; a muted dash when undetermined."""
    if approach is None and sideways is None:
        ui.label("—").classes("tk-muted")
        return
    icon = DIRECTION_ICONS.get(approach or "", "arrow_back" if sideways == "left" else "arrow_forward")
    with ui.row().classes("items-center gap-1 no-wrap"):
        ui.icon(icon).classes("text-base tk-green")
        ui.label(text)
        ui.tooltip("Worked out from how the vehicle's box grew, shrank or moved across the picture.")


def registry_cell(match, status: str) -> None:
    """Match (green), Possible match (amber, one character away, never asserted), No match, or nothing."""
    if match is not None and match.exact:
        ui.label("Match").classes("tk-green font-medium")
    elif match is not None:
        with ui.row().classes("items-center gap-1 no-wrap tk-amber"):
            ui.icon("help_outline").classes("text-base")
            ui.label("Possible match").classes("font-medium")
            ui.tooltip(
                f"The registry has {match.record.registration_number}, one character away ({match.difference}). "
                "Not asserted: the recognised number is shown as read."
            )
    elif status == "confirmed":
        ui.label("No match").classes("tk-secondary")
    else:
        ui.label("—").classes("tk-muted")


def detections_table(
    rows: list[DetectionRow],
    columns: tuple[str, ...],
    on_row: Callable[[DetectionRow], object],
    sort: str | None = None,
    descending: bool = True,
    on_sort: Callable[[str], object] | None = None,
) -> None:
    """Render the rows; headers of sortable columns call `on_sort(column)` when `on_sort` is given."""
    with ui.element("div").classes("tk-table-wrap w-full"), ui.element("table").classes("tk-html-table"):
        with ui.element("thead"), ui.element("tr"):
            for column in columns:
                with ui.element("th"):
                    sortable = on_sort is not None and column not in ("plate", "registry")
                    if sortable:
                        arrow = (" ▼" if descending else " ▲") if column == sort else ""
                        ui.button(COLUMNS[column] + arrow, color=None, on_click=lambda _, c=column: on_sort(c)).props(
                            "flat dense no-caps"
                        ).classes("tk-th-button")
                    else:
                        ui.label(COLUMNS[column])
        with ui.element("tbody"):
            for row in rows:
                d = row.detection
                tr = ui.element("tr").classes("tk-row")
                tr.on("click", lambda _, r=row: on_row(r))
                with tr:
                    for column in columns:
                        with ui.element("td"):
                            if column == "time":
                                ui.label(video_time(d.first_seen_s)).classes("tk-mono")
                            elif column == "video":
                                ui.label(d.video_name)
                            elif column == "track":
                                ui.label(f"T{d.track_id}")
                            elif column == "vehicle_type":
                                shown_type = row.correction.corrected_type if row.correction else None
                                with ui.row().classes("items-center gap-2 no-wrap"):
                                    ui.icon(VEHICLE_ICONS.get(shown_type or d.vehicle_type, "directions_car")).classes(
                                        "text-lg tk-secondary"
                                    )
                                    if shown_type:
                                        corrected_value(shown_type, d.vehicle_type, row.correction.corrected_by)
                                    else:
                                        ui.label(d.vehicle_type)
                            elif column == "direction":
                                direction_cell(d.approach, d.sideways, d.direction_short)
                            elif column == "registration_number":
                                shown_number = row.correction.corrected_number if row.correction else None
                                if shown_number:
                                    corrected_value(
                                        shown_number, d.registration_number or "nothing", row.correction.corrected_by
                                    ).classes("font-semibold tk-mono")
                                else:
                                    ui.label(d.registration_number or "—").classes("font-semibold tk-mono")
                            elif column == "confidence":
                                ui.label(f"{d.confidence:.2f}" if d.status != "not_detected" else "—").classes(
                                    "tk-mono"
                                )
                            elif column == "status":
                                status_badge(d.status)
                            elif column == "registry":
                                registry_cell(row.registry_match, d.status)
                            elif column == "plate":
                                if image_url(d.plate_crop_path):
                                    ui.image(image_url(d.plate_crop_path)).classes("tk-plate-thumb")
                                else:
                                    ui.label("—").classes("tk-muted")
