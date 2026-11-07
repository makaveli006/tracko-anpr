"""The details of one detection (DESIGN section 12): crops, the number, the evidence, the registry match."""

from __future__ import annotations

from nicegui import ui

from tracko_anpr.dashboard.format import STATUS_LABELS, VEHICLE_ICONS, percent, video_time
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.services import results
from tracko_anpr.services.registry import DISCLAIMER
from tracko_anpr.services.results import DetectionDetail


def image_url(path: str | None) -> str | None:
    return f"/api/images/{path}" if path else None


def status_badge(status: str, confidence: float | None = None) -> None:
    """Confirmed: green check and text; unconfirmed: amber; not detected: gray."""
    colour = {"confirmed": "tk-green", "unconfirmed": "tk-amber"}.get(status, "tk-muted")
    icon = {"confirmed": "check_circle", "unconfirmed": "warning"}.get(status, "remove_circle_outline")
    with ui.row().classes(f"items-center gap-1 no-wrap {colour}"):
        ui.icon(icon).classes("text-base")
        ui.label(STATUS_LABELS.get(status, status)).classes("font-medium")


async def show_detection(track_pk: int, open_in_analysis: str | None = None) -> None:
    """Open the details dialog; `open_in_analysis` adds a button that leads to the player at that moment."""
    detail: DetectionDetail | None = await query(results.detection_detail, track_pk)
    if detail is None:
        ui.notify("That detection is no longer in the database.", type="warning")
        return
    d = detail.detection
    with ui.dialog() as dialog, ui.card().classes("tk-card").style("min-width: 820px; max-width: 95vw"):
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.row().classes("items-center gap-3 no-wrap"):
                ui.icon(VEHICLE_ICONS.get(d.vehicle_type, "directions_car")).classes("text-3xl tk-green")
                with ui.column().classes("gap-0"):
                    ui.label(f"T{d.track_id} · {d.vehicle_type}").classes("tk-card-title")
                    ui.label(
                        f"{d.video_name} · seen {video_time(d.first_seen_s)} to {video_time(d.last_seen_s)}"
                    ).classes("tk-secondary text-sm")
            with ui.row().classes("items-center gap-2 no-wrap"):
                if open_in_analysis:
                    ui.button(
                        "Open in Video Analysis",
                        color=None,
                        icon="play_circle",
                        on_click=lambda: ui.navigate.to(open_in_analysis),
                    ).classes("tk-primary")
                ui.button(color=None, icon="close", on_click=dialog.close).props("flat round").classes("tk-link")

        with ui.row().classes("w-full gap-5 no-wrap items-start mt-2"):
            with ui.column().classes("gap-2").style("flex: 0 0 300px"):
                ui.label("Vehicle").classes("tk-muted text-xs uppercase")
                if image_url(d.vehicle_crop_path):
                    ui.image(image_url(d.vehicle_crop_path)).classes("w-full rounded-lg").style(
                        "max-height: 260px; object-fit: contain; background: #000"
                    )
                else:
                    ui.label("No vehicle crop kept").classes("tk-muted")
                ui.label("Number plate").classes("tk-muted text-xs uppercase mt-2")
                if image_url(d.plate_crop_path):
                    ui.image(image_url(d.plate_crop_path)).classes("rounded").style(
                        "width: 100%; max-height: 110px; object-fit: contain; background: #000; image-rendering: auto"
                    )
                else:
                    ui.label("No plate found").classes("tk-muted")
            with ui.column().classes("gap-3").style("flex: 1 1 0; min-width: 0"):
                with ui.element("div").classes("tk-kv"):
                    ui.label("Registration").classes("k")
                    ui.label(d.registration_number or "—").classes("v text-lg font-semibold tk-mono")
                    ui.label("Validation").classes("k")
                    with ui.element("div").classes("v"):
                        status_badge(d.status)
                    ui.label("Confidence").classes("k")
                    ui.label(
                        f"{d.confidence:.2f} (average of the agreeing readings; not accuracy)"
                        if d.status != "not_detected"
                        else "—"
                    ).classes("v")
                    ui.label("Agreement").classes("k")
                    ui.label(
                        f"{d.support} of {d.readings} readings agree ({percent(detail.share) if d.readings else '—'})"
                    ).classes("v")
                    ui.label("Reason").classes("k")
                    ui.label(d.reason or "—").classes("v")
                    ui.label("Detector").classes("k")
                    ui.label(
                        f"{d.vehicle_type} at {d.detection_confidence:.2f}, {detail.frames_seen:,} frames"
                    ).classes("v")
                    if detail.same_vehicle_as is not None:
                        ui.label("Same vehicle as").classes("k")
                        ui.label(f"T{detail.same_vehicle_as} (not counted again)").classes("v")
                    ui.label("Demo registry").classes("k")
                    with ui.element("div").classes("v"):
                        if detail.registry_match is not None:
                            r = detail.registry_match
                            ui.label(
                                f"Match · {r.owner_name} · {r.vehicle_description} · {r.colour} · {r.registered_at}"
                            ).classes("tk-green")
                        elif d.status == "confirmed":
                            ui.label("No match").classes("tk-secondary")
                        else:
                            ui.label("Not looked up (number not confirmed)").classes("tk-muted")
                        ui.label(DISCLAIMER).classes("tk-muted text-xs")

                ui.label(f"Multi-frame observations ({len(detail.observations)} plates examined)").classes(
                    "tk-muted text-xs uppercase mt-1"
                )
                if detail.observations:
                    columns = [
                        {"name": "time", "label": "Time", "field": "time", "align": "left"},
                        {"name": "frame", "label": "Frame", "field": "frame", "align": "right"},
                        {"name": "text", "label": "Reading", "field": "text", "align": "left"},
                        {"name": "conf", "label": "Reader conf.", "field": "conf", "align": "right"},
                        {"name": "det", "label": "Plate conf.", "field": "det", "align": "right"},
                        {"name": "width", "label": "Width px", "field": "width", "align": "right"},
                    ]
                    rows = [
                        {
                            "time": video_time(o.time_s),
                            "frame": o.frame,
                            "text": "(unreadable)" if o.unreadable else (o.text or "—"),
                            "conf": f"{o.ocr_confidence:.2f}",
                            "det": f"{o.detector_confidence:.2f}",
                            "width": round(o.box[2] - o.box[0]),
                        }
                        for o in detail.observations
                    ]
                    ui.table(columns=columns, rows=rows).classes("w-full tk-table").props("flat dense").style(
                        "max-height: 260px"
                    )
                else:
                    ui.label("No plate was found on this vehicle in any of its examined frames.").classes("tk-muted")
    dialog.open()
