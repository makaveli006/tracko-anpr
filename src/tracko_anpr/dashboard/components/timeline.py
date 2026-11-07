"""The seven-stage processing timeline (DESIGN section 9), drawn from a real `JobStatus`."""

from __future__ import annotations

from datetime import datetime

from nicegui import ui

from tracko_anpr.pipeline.runner import STAGES
from tracko_anpr.services.jobs import JobStatus

STAGE_TITLES = {
    "video_uploaded": "Video Uploaded",
    "vehicle_detection": "Vehicle Detection (YOLO26m)",
    "vehicle_tracking": "Vehicle Tracking (TrackTrack)",
    "plate_detection": "Plate Detection (YOLO26s)",
    "ocr": "OCR (Awiros-ANPR-OCR)",
    "validation": "Multi-frame Validation",
    "result_generation": "Result Generation",
}

ICONS = {"done": "check_circle", "running": "pending", "pending": "radio_button_unchecked", "failed": "cancel"}


def _when(moment: datetime | None) -> str:
    return moment.astimezone().strftime("%d %b %Y, %H:%M:%S") if moment else ""


def banner(job: JobStatus | None) -> None:
    if job is None:
        with ui.element("div").classes("tk-banner gray"):
            ui.icon("hourglass_empty")
            ui.label("Not processed")
    elif job.status == "completed":
        with ui.element("div").classes("tk-banner green"):
            ui.icon("check_circle")
            ui.label("Completed")
    elif job.status == "failed":
        with ui.element("div").classes("tk-banner red"):
            ui.icon("error")
            ui.label("Failed")
    elif job.status == "processing":
        with ui.element("div").classes("tk-banner amber"):
            ui.icon("autorenew")
            ui.label("Stalled — the worker has stopped reporting" if job.stalled else f"Processing  {job.progress:.0%}")
    else:
        with ui.element("div").classes("tk-banner gray"):
            ui.icon("schedule")
            ui.label("Queued — waiting for the worker")


def timeline(job: JobStatus | None, uploaded_at: datetime | None = None) -> None:
    """Banner plus the seven stages; every state comes from the job row, nothing is assumed."""
    banner(job)
    with ui.element("div").classes("tk-timeline"):
        for index, name in enumerate(STAGES):
            state = job.stages[index] if job else None
            status = state.status if state else "pending"
            if job is not None and job.status == "failed" and job.stage_index is not None and index == job.stage_index:
                status = "failed"
            if index == 0 and job is not None:
                status = "done"
            if name == "vehicle_detection" and job is not None and job.stage == "vehicle_tracking" and status == "done":
                status = "running"  # detection and tracking are one pass over the video; both are under way
                state = job.stages[index + 1]
            with ui.element("div").classes(f"tk-stage {status}"):
                with ui.element("div").classes("tk-stage-marker"):
                    ui.icon(ICONS[status])
                    ui.element("div").classes("tk-stage-line")
                with ui.column().classes("gap-0"):
                    ui.label(STAGE_TITLES[name]).classes("tk-stage-name")
                    ui.label(_stage_detail(name, status, state, job, uploaded_at)).classes("tk-stage-detail")
        if job is not None and job.status == "failed" and job.error:
            ui.label(job.error).classes("tk-red text-sm").style("white-space: pre-wrap")


def _stage_detail(name: str, status: str, state, job: JobStatus | None, uploaded_at: datetime | None) -> str:
    if name == "video_uploaded":
        return _when(uploaded_at) or ("Completed" if status == "done" else "")
    if status == "running" and state is not None and state.total:
        unit = "plates" if name == "ocr" else "vehicles" if name == "validation" else "frames"
        return f"{state.done:,} / {state.total:,} {unit} ({100 * state.done / state.total:.0f}%)"
    if status == "running":
        return "Starting…"
    if status == "failed":
        return "Failed"
    if status == "done":
        if job is not None and job.timings:
            key = {
                "vehicle_detection": "detection_and_tracking_s",
                "vehicle_tracking": "detection_and_tracking_s",
                "plate_detection": "plate_detection_s",
                "ocr": "ocr_s",
                "validation": "validation_s",
                "result_generation": "result_generation_s",
            }.get(name)
            seconds = job.timings.get(key) if key else None
            if seconds is not None:
                return f"Completed in {seconds:.0f} s" if seconds >= 1 else "Completed"
        return "Completed"
    return "Pending"
