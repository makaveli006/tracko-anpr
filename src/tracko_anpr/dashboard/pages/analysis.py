"""Video Analysis (DESIGN section 15): one video, large, with every tracked vehicle beside it.

Original / annotated comparison, the player at full width, the track list as a timeline (a
click seeks the video and opens the details), plate recognition figures and the downloads.
`?t=<seconds>` seeks on arrival, which is how a Detection History row lands here.
"""

from __future__ import annotations

from nicegui import ui

from tracko_anpr.dashboard.components.detection_dialog import show_detection
from tracko_anpr.dashboard.components.detections_table import detections_table
from tracko_anpr.dashboard.components.player import VideoPlayer
from tracko_anpr.dashboard.components.timeline import timeline
from tracko_anpr.dashboard.format import human_duration, percent, thousands, when
from tracko_anpr.dashboard.layout import frame
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.services import jobs, results, videos
from tracko_anpr.services.results import DetectionRow

DOWNLOADS = (
    ("annotated", "Annotated video", "movie"),
    ("results", "Results (JSON)", "data_object"),
    ("detections", "Detections (CSV)", "table_view"),
    ("plates", "Plates (CSV)", "table_view"),
)


def _load(session, video_id: int | None):
    processed = [v for v in videos.list_videos(session) if v.completed_job_id is not None]
    selected = next((v for v in processed if v.id == video_id), None) if video_id is not None else None
    if selected is None and video_id is None and processed:
        selected = processed[0]
    if selected is None:
        return processed, None, None, None, []
    found = results.video_results(session, selected.id)
    job = jobs.get_job(session, found.job_id) if found and found.job_id else None
    rows = results.video_detections(session, selected.id, newest_first=False)
    return processed, selected, found, job, rows


class AnalysisPage:
    def __init__(self, processed, selected, found, job, rows: list[DetectionRow], start_at: float | None) -> None:
        self.processed, self.selected, self.found, self.job, self.rows = processed, selected, found, job, rows
        self.start_at = start_at
        self.player: VideoPlayer | None = None

    def build(self) -> None:
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            options = {v.id: v.name for v in self.processed}
            selector = (
                ui.select(
                    options,
                    value=self.selected.id if self.selected else None,
                    label="Video",
                    on_change=lambda e: ui.navigate.to(f"/analysis?video={e.value}"),
                )
                .props("outlined dense dark options-dense")
                .style("min-width: 260px")
            )
            if not options:
                selector.disable()
            if self.selected:
                with ui.row().classes("gap-2 no-wrap"):
                    for kind, label, icon in DOWNLOADS:
                        target = f"/api/videos/{self.selected.id}/download/{kind}"
                        ui.button(
                            label, color=None, icon=icon, on_click=lambda _, t=target: ui.navigate.to(t, new_tab=True)
                        ).classes("tk-secondary")
        with ui.row().classes("w-full gap-4 no-wrap items-start"):
            with ui.column().classes("gap-4").style("flex: 7 1 0; min-width: 0"):
                with ui.element("div").classes("tk-card w-full"):
                    self.player = VideoPlayer()
                    if self.selected and self.found:
                        self.player.show(self.selected, has_annotated=bool(self.found.annotated_video_path))
                        if self.start_at is not None:
                            ui.timer(1.2, lambda: self.player.seek(self.start_at, play=False), once=True)
                    else:
                        self.player.empty("No processed video yet. Upload one on the Upload & Process page.")
                with ui.element("div").classes("tk-card w-full"):
                    self.tracks_card()
            with ui.column().classes("gap-4").style("flex: 3 1 0; min-width: 300px"):
                with ui.element("div").classes("tk-card w-full"):
                    self.recognition_card()
                with ui.element("div").classes("tk-card w-full"):
                    ui.label("Processing Status").classes("tk-card-title mb-2")
                    timeline(self.job, self.selected.created_at if self.selected else None)

    def recognition_card(self) -> None:
        ui.label("Plate Recognition").classes("tk-card-title")
        if not self.found:
            ui.label("Nothing processed yet.").classes("tk-muted mt-2")
            return
        s, v = self.found.summary, self.selected
        with ui.element("div").classes("tk-kv mt-2"):
            for key, value in (
                (
                    "Video",
                    f"{v.original_filename} · {v.width}×{v.height} @ {v.fps_decimal:.2f} fps · "
                    f"{human_duration(v.duration_s)}",
                ),
                ("Processed", when(self.found.processed_at, seconds=True)),
                ("Unique tracks", thousands(s.unique_tracks)),
                ("Counted vehicles", thousands(s.total_vehicles)),
                (
                    "Confirmed numbers",
                    f"{thousands(s.confirmed_plates)} ({percent(s.recognition_coverage)} coverage, not accuracy)",
                ),
                ("Unconfirmed", thousands(self.found.by_status.get("unconfirmed", 0))),
                ("No plate found", thousands(self.found.by_status.get("not_detected", 0))),
                ("By type", ", ".join(f"{k} {n}" for k, n in self.found.by_class.items())),
                (
                    "Processing time",
                    human_duration(s.average_processing_seconds) if s.average_processing_seconds else "—",
                ),
            ):
                ui.label(key).classes("k")
                ui.label(value).classes("v")

    def tracks_card(self) -> None:
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Tracked Vehicles").classes("tk-card-title")
            ui.label(f"{len(self.rows)} counted vehicles, in order of appearance").classes("tk-secondary text-sm")
        if not self.rows:
            ui.label("No vehicles.").classes("tk-muted mt-2")
            return
        with ui.element("div").classes("w-full mt-2").style("max-height: 520px; overflow: auto"):
            detections_table(
                self.rows,
                ("time", "track", "vehicle_type", "registration_number", "confidence", "status", "registry", "plate"),
                self.row_clicked,
            )
        ui.label("Click a vehicle to jump the video to its first appearance and see the details.").classes(
            "tk-muted text-xs mt-1"
        )

    async def row_clicked(self, row: DetectionRow) -> None:
        if self.player is not None:
            self.player.seek(max(0.0, row.detection.first_seen_s - 0.5), play=False)
        await show_detection(row.detection.track_pk)


@ui.page("/analysis")
async def analysis_page(video: int | None = None, t: float | None = None) -> None:
    processed, selected, found, job, rows = await query(_load, video)
    with frame("analysis", "Video Analysis", "Original and annotated playback with every tracked vehicle"):
        AnalysisPage(processed, selected, found, job, rows, t).build()
