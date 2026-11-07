"""The details of one detection (DESIGN section 12): crops, the number, the evidence, the registry match,
and the place where an operator corrects a wrong number or vehicle type.

A correction is stored beside the system's result, never over it (services/corrections.py): the
dialog shows both, and the dashboard's figures keep counting the system's answer.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from nicegui import ui

from tracko_anpr.dashboard.format import STATUS_LABELS, VEHICLE_ICONS, percent, video_time, when
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.services import corrections, results
from tracko_anpr.services.corrections import VEHICLE_TYPES, CorrectionError
from tracko_anpr.services.registry import DISCLAIMER
from tracko_anpr.services.results import DetectionDetail

OPERATOR_KEY = "tk_operator"  # the operator's name, remembered in the browser's local storage
EVENT_ICONS = {
    "new": "fiber_manual_record",
    "read": "visibility",
    "confirmed": "check_circle",
    "corrected": "edit",
    "lost": "logout",
}


def image_url(path: str | None) -> str | None:
    return f"/api/images/{path}" if path else None


def status_badge(status: str, confidence: float | None = None) -> None:
    """Confirmed: green check and text; unconfirmed: amber; not detected: gray."""
    colour = {"confirmed": "tk-green", "unconfirmed": "tk-amber"}.get(status, "tk-muted")
    icon = {"confirmed": "check_circle", "unconfirmed": "warning"}.get(status, "remove_circle_outline")
    with ui.row().classes(f"items-center gap-1 no-wrap {colour}"):
        ui.icon(icon).classes("text-base")
        ui.label(STATUS_LABELS.get(status, status)).classes("font-medium")


async def show_detection(
    track_pk: int,
    open_in_analysis: str | None = None,
    on_change: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Open the details dialog.

    `open_in_analysis` adds a button that leads to the player at that moment; `on_change` is awaited
    after a correction is saved or undone, so the page behind can redraw its table.
    """
    detail: DetectionDetail | None = await query(results.detection_detail, track_pk)
    if detail is None:
        ui.notify("That detection is no longer in the database.", type="warning")
        return
    try:
        operator = str(await ui.run_javascript(f"localStorage.getItem({json.dumps(OPERATOR_KEY)}) || ''") or "")
    except Exception:  # a slow or closed client: start with an empty name
        operator = ""

    # The dialog is anchored to the page's content, not to the element that was clicked: the click comes
    # from a table row, and redrawing the table after a correction would otherwise delete the dialog too.
    with ui.context.client.content:
        dialog = ui.dialog()
        with dialog, ui.card().classes("tk-card").style("min-width: 860px; max-width: 95vw"):
            body = ui.element("div").classes("w-full")

    async def changed() -> None:
        nonlocal detail
        detail = await query(results.detection_detail, track_pk)
        render()
        if on_change is not None:
            await on_change()

    async def save(number_box, type_box, name_box, note_box) -> None:
        nonlocal operator
        name = (name_box.value or "").strip()
        try:
            await query(
                corrections.save_correction, track_pk, number_box.value, type_box.value, name, note_box.value or ""
            )
        except CorrectionError as error:
            ui.notify(str(error), type="negative", close_button=True)
            return
        operator = name  # the redrawn form keeps the name, and the browser remembers it for next time
        ui.run_javascript(f"localStorage.setItem({json.dumps(OPERATOR_KEY)}, {json.dumps(name)})")
        ui.notify("Correction saved. The system's result is kept beside it.", type="positive")
        await changed()

    async def undo() -> None:
        await query(corrections.undo_latest, track_pk)
        ui.notify("Correction removed.", type="info")
        await changed()

    def render() -> None:
        d = detail.detection
        current = detail.correction
        body.clear()
        with body:
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.row().classes("items-center gap-3 no-wrap"):
                    ui.icon(VEHICLE_ICONS.get(d.vehicle_type, "directions_car")).classes("text-3xl tk-green")
                    with ui.column().classes("gap-0"):
                        ui.label(f"T{d.track_id} · {d.vehicle_type} · {d.direction_label}").classes("tk-card-title")
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
                            "width: 100%; max-height: 110px; object-fit: contain; background: #000"
                        )
                    else:
                        ui.label("No plate found").classes("tk-muted")
                    correction_box(current)

                with ui.column().classes("gap-3").style("flex: 1 1 0; min-width: 0"):
                    facts(d, current)
                    events(d)
                    observations()

    def facts(d, current) -> None:
        with ui.element("div").classes("tk-kv"):
            ui.label("Registration").classes("k")
            with ui.column().classes("v gap-0"):
                ui.label(d.registration_number or "—").classes("text-lg font-semibold tk-mono")
                if current is not None and current.corrected_number:
                    with ui.row().classes("items-center gap-1 no-wrap tk-amber"):
                        ui.icon("edit").classes("text-sm")
                        ui.label(f"Corrected to {current.corrected_number}").classes("font-semibold tk-mono")
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
            with ui.column().classes("v gap-0"):
                ui.label(f"{d.vehicle_type} at {d.detection_confidence:.2f}, {detail.frames_seen:,} frames")
                if current is not None and current.corrected_type:
                    with ui.row().classes("items-center gap-1 no-wrap tk-amber"):
                        ui.icon("edit").classes("text-sm")
                        ui.label(f"Corrected to {current.corrected_type}").classes("font-medium")
            if detail.same_vehicle_as is not None:
                ui.label("Same vehicle as").classes("k")
                ui.label(f"T{detail.same_vehicle_as} (not counted again)").classes("v")
            ui.label("Demo registry").classes("k")
            with ui.element("div").classes("v"):
                if detail.registry_match is not None and detail.registry_match.exact:
                    r = detail.registry_match.record
                    ui.label(
                        f"Match · {r.owner_name} · {r.vehicle_description} · {r.colour} · {r.registered_at}"
                    ).classes("tk-green")
                elif detail.registry_match is not None:
                    m = detail.registry_match
                    r = m.record
                    ui.label(
                        f"Possible match · {r.registration_number} · {r.owner_name} · {r.vehicle_description} · "
                        f"{r.colour} · {r.registered_at}"
                    ).classes("tk-amber")
                    ui.label(
                        f"One character differs ({m.difference}); the number is not asserted to be this record."
                        + (f" {m.others} more record(s) are also one character away." if m.others else "")
                    ).classes("tk-muted text-xs")
                elif d.status == "confirmed":
                    ui.label("No match").classes("tk-secondary")
                else:
                    ui.label("Not looked up (number not confirmed)").classes("tk-muted")
                ui.label(DISCLAIMER).classes("tk-muted text-xs")

    def events(d) -> None:
        """The track's life on the video, in the manner of a New / Update / Lost event stream."""
        ui.label("Events").classes("tk-muted text-xs uppercase mt-1")
        with ui.element("div").classes("tk-events w-full"):
            for e in detail.events:
                row = ui.element("div").classes(f"tk-event {e.kind}")
                with row:
                    ui.icon(EVENT_ICONS.get(e.kind, "circle")).classes("tk-event-icon")
                    moment = video_time(e.time_s) if e.time_s is not None else when(e.at, seconds=True)
                    ui.label(moment).classes("tk-mono tk-event-time")
                    ui.label(e.text).classes("tk-event-text")
                    ui.label(f"frame {e.frame:,}" if e.frame is not None else "wall-clock time").classes(
                        "tk-muted text-xs"
                    )
                if open_in_analysis and e.time_s is not None:
                    target = f"/analysis?video={d.video_id}&t={max(0.0, e.time_s - 0.5):.2f}"
                    row.classes("clickable").on("click", lambda _, url=target: ui.navigate.to(url))
        ui.label(
            "Reconstructed from the stored frames and readings: nothing is logged while a video is processed. "
            "A correction is the only event with a wall-clock time."
        ).classes("tk-muted text-xs")

    def observations() -> None:
        ui.label(f"Multi-frame observations ({len(detail.observations)} plates examined)").classes(
            "tk-muted text-xs uppercase mt-1"
        )
        if not detail.observations:
            ui.label("No plate was found on this vehicle in any of its examined frames.").classes("tk-muted")
            return
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
        ui.table(columns=columns, rows=rows).classes("w-full tk-table").props("flat dense").style("max-height: 220px")

    def correction_box(current) -> None:
        """Where an operator corrects the number or the type, and sees what was corrected before."""
        d = detail.detection
        with ui.element("div").classes("tk-correction-box w-full mt-3"):
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.icon("edit").classes("tk-amber")
                ui.label("Correct this detection").classes("font-semibold")
            if current is not None:
                parts = []
                if current.corrected_number:
                    parts.append(f"number {current.corrected_number} (system: {current.system_number or 'none'})")
                if current.corrected_type:
                    parts.append(f"type {current.corrected_type} (system: {current.system_type})")
                by = f" by {current.corrected_by}" if current.corrected_by else ""
                ui.label(f"Corrected to {' and '.join(parts)}{by}, {when(current.created_at, seconds=True)}.").classes(
                    "tk-amber text-sm mt-1"
                )
                if current.note:
                    ui.label(f"Note: {current.note}").classes("tk-secondary text-xs")
                if len(detail.corrections) > 1:
                    ui.label(f"{len(detail.corrections)} corrections made to this detection in all.").classes(
                        "tk-muted text-xs"
                    )
            number_box = (
                ui.input("Registration number", value=(current.corrected_number if current else "") or "")
                .props("outlined dense dark uppercase placeholder=KL07AB1234")
                .classes("w-full mt-2")
            )
            type_box = (
                ui.select(
                    list(VEHICLE_TYPES),
                    value=(current.corrected_type if current and current.corrected_type else d.vehicle_type),
                    label="Vehicle type",
                )
                .props("outlined dense dark options-dense")
                .classes("w-full")
            )
            name_box = ui.input("Your name (optional)", value=operator).props("outlined dense dark").classes("w-full")
            note_box = ui.input("Note (optional)").props("outlined dense dark").classes("w-full")
            with ui.row().classes("gap-2 mt-2 items-center"):
                ui.button(
                    "Save correction",
                    color=None,
                    icon="save",
                    on_click=lambda: save(number_box, type_box, name_box, note_box),
                ).classes("tk-primary")
                if current is not None:
                    ui.button("Undo", color=None, icon="undo", on_click=undo).props("flat").classes("tk-link")
            ui.label("Kept beside the system's result for evaluation; the dashboard's figures do not change.").classes(
                "tk-muted text-xs mt-1"
            )

    render()
    dialog.open()
