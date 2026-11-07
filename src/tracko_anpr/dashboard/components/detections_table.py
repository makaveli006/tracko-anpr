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
    "registration_number": "Registration Number",
    "confidence": "Confidence",
    "status": "Validation",
    "registry": "Demo Registry",
    "plate": "Plate Image",
}


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
                                with ui.row().classes("items-center gap-2 no-wrap"):
                                    ui.icon(VEHICLE_ICONS.get(d.vehicle_type, "directions_car")).classes(
                                        "text-lg tk-secondary"
                                    )
                                    ui.label(d.vehicle_type)
                            elif column == "registration_number":
                                ui.label(d.registration_number or "—").classes("font-semibold tk-mono")
                            elif column == "confidence":
                                ui.label(f"{d.confidence:.2f}" if d.status != "not_detected" else "—").classes(
                                    "tk-mono"
                                )
                            elif column == "status":
                                status_badge(d.status)
                            elif column == "registry":
                                if row.registry_match is not None:
                                    ui.label("Match").classes("tk-green font-medium")
                                elif d.status == "confirmed":
                                    ui.label("No match").classes("tk-secondary")
                                else:
                                    ui.label("—").classes("tk-muted")
                            elif column == "plate":
                                if image_url(d.plate_crop_path):
                                    ui.image(image_url(d.plate_crop_path)).classes("tk-plate-thumb")
                                else:
                                    ui.label("—").classes("tk-muted")
