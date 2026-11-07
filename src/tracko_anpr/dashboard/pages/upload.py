"""Upload & Process (DESIGN section 14): upload an MP4, see what it is, start processing, watch it run.

Nothing here is simulated. The file goes through the same checks as the API's upload, the
"Process Video" button inserts a queued job, and the timeline and progress bar are redrawn
every second from the job row the worker writes. A failed job shows its reason in red.

Every new video also gets a plate-size check (pipeline/plate_check.py): the worker samples a few
frames and reports how wide the plates are, so the user knows before the full run whether the
recording can work. The File Information card shows it; "Check again" asks for a fresh one.
"""

from __future__ import annotations

from pathlib import Path

from nicegui import events, ui

from tracko_anpr.dashboard.components.timeline import timeline
from tracko_anpr.dashboard.format import human_duration, human_size, when
from tracko_anpr.dashboard.layout import frame
from tracko_anpr.dashboard.runtime import query, runtime
from tracko_anpr.pipeline.plate_check import BORDERLINE, GOOD, GOOD_WIDTH, LOW
from tracko_anpr.services import jobs, videos
from tracko_anpr.services.jobs import JobStatus
from tracko_anpr.services.videos import MAX_UPLOAD_BYTES, InvalidVideo, PlateCheckState, VideoSummary

POLL_SECONDS = 1.0
GUIDE = Path(__file__).resolve().parents[3].parent / "RECORDING_GUIDE.md"
"""The recording guide at the project root; the Upload page shows its first sections."""


def recording_tips() -> str:
    """Sections 1 to 3 of RECORDING_GUIDE.md (what the system needs, where to stand, how to record)."""
    try:
        text = GUIDE.read_text(encoding="utf-8")
    except OSError:
        return "See RECORDING_GUIDE.md in the project folder."
    start = text.find("## 1.")
    end = text.find("## 4.")
    body = text[start:end] if start != -1 and end != -1 else text
    return body.replace("## ", "#### ")


class UploadPage:
    def __init__(self) -> None:
        self.video: VideoSummary | None = None
        self.job: JobStatus | None = None
        self.poller: ui.timer | None = None

    # --- building ----------------------------------------------------------------------------

    def build(self) -> None:
        with ui.row().classes("w-full gap-4 no-wrap items-start"):
            with ui.column().classes("gap-4").style("flex: 3 1 0; min-width: 0"):
                self.upload_card()
                self.file_card = ui.element("div").classes("tk-card w-full")
                self.videos_card = ui.element("div").classes("tk-card w-full")
            with ui.column().classes("gap-4").style("flex: 2 1 0; min-width: 320px"):
                self.status_card = ui.element("div").classes("tk-card w-full")
        # Created once, here, in the page's own context: an event handler runs in the context of the
        # element that fired it, and that element may have been redrawn away by the time it needs a timer.
        self.poller = ui.timer(POLL_SECONDS, self.poll, active=False)
        self.render_file()
        self.render_status()
        ui.timer(0.1, self.refresh_videos, once=True)

    def upload_card(self) -> None:
        with ui.element("div").classes("tk-card w-full tk-dropzone"):
            with ui.column().classes("items-center w-full gap-1 pb-3"):
                ui.icon("cloud_upload").classes("text-5xl").style("color: #ffffff")
                ui.label("Upload Road Traffic Video").classes("text-xl font-semibold")
                ui.label("Upload an MP4 video to analyze vehicle movement and registration plates.").classes(
                    "tk-secondary"
                )
                ui.label("MP4 video · H.264 preferred · 1080p and 30 frames per second recommended").classes(
                    "tk-muted text-xs"
                )
            with ui.expansion("Recording tips for better results", icon="videocam").classes("w-full tk-tips"):
                ui.markdown(recording_tips()).classes("tk-secondary text-sm tk-tips-body")
                ui.label(
                    f"Plate at least {GOOD_WIDTH} px wide, camera in line with the traffic, 1080p at 30 fps. "
                    "The full guide is RECORDING_GUIDE.md in the project folder."
                ).classes("tk-muted text-xs mt-1")
            self.uploader = (
                ui.upload(
                    label="Drop an MP4 here or click to choose",
                    auto_upload=True,
                    max_file_size=MAX_UPLOAD_BYTES,
                    max_files=1,
                    on_upload=self.on_upload,
                    on_rejected=lambda: ui.notify(
                        "That file was not accepted: it must be an .mp4 under 8 GB.", type="warning"
                    ),
                )
                .props('accept=".mp4,video/mp4" flat')
                .classes("w-full")
            )

    # --- the upload ----------------------------------------------------------------------------

    async def on_upload(self, event: events.UploadEventArguments) -> None:
        upload = event.file
        try:
            original = videos.check_upload_name(upload.name)
        except InvalidVideo as error:
            ui.notify(str(error), type="negative", close_button=True)
            self.uploader.reset()
            return
        part = videos.incoming_path(runtime.settings, original)
        ui.notify(f"Saving {original}…", type="info")
        try:
            await upload.save(part)
            self.video = await query(videos.adopt_upload, runtime.settings, Path(part), original)
        except InvalidVideo as error:
            ui.notify(str(error), type="negative", close_button=True, timeout=0)
            self.uploader.reset()
            return
        self.job = None
        self.uploader.reset()
        ui.notify(f"{original} uploaded as {self.video.name}.", type="positive")
        self.render_file()
        self.render_status()
        self.start_polling()  # the plate-size check was requested with the upload
        await self.refresh_videos()

    # --- file information and the process button -------------------------------------------------

    def render_file(self) -> None:
        self.file_card.clear()
        with self.file_card:
            ui.label("File Information").classes("tk-card-title")
            video = self.video
            if video is None:
                ui.label("No video selected. Upload one above, or pick one from the list below.").classes(
                    "tk-muted mt-2"
                )
                return
            with ui.element("div").classes("tk-kv mt-3"):
                for key, value in (
                    ("Filename", video.original_filename),
                    ("Stored as", video.name),
                    ("File size", human_size(video.size_bytes)),
                    ("Resolution", f"{video.width} × {video.height}"),
                    ("Duration", human_duration(video.duration_s)),
                    ("Frame rate", f"{video.fps_decimal:.2f} fps ({video.frame_count:,} frames)"),
                    ("Uploaded", when(video.created_at)),
                    ("Upload status", "Stored and readable" if video.source == "upload" else "Registered from disk"),
                ):
                    ui.label(key).classes("k")
                    ui.label(value).classes("v")
                ui.label("Plate-size check").classes("k")
                with ui.column().classes("v gap-0"):
                    self.plate_check_lines(video.plate_check)
            with ui.row().classes("mt-4 gap-3 items-center"):
                busy = self.job is not None and self.job.status in ("queued", "processing")
                label = (
                    "Processing…" if busy else "Process Video" if video.completed_job_id is None else "Process Again"
                )
                button = ui.button(label, color=None, icon="play_arrow", on_click=self.start).classes("tk-primary")
                if busy:
                    button.disable()
                if video.completed_job_id is not None:
                    ui.label("Processed before; the dashboard shows the latest result.").classes("tk-muted text-sm")

    def plate_check_lines(self, state: PlateCheckState | None) -> None:
        """The plate-size check's state: a spinner while it runs, the verdict in the theme's colours when done."""
        if state is None:
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.label("Not checked").classes("tk-muted")
                self.check_link("Check now")
            return
        if state.live:
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.spinner(size="sm").classes("tk-green")
                ui.label(
                    "Checking plate sizes: a few sampled frames, about half a minute"
                    + (" (waiting for the worker)" if state.status == "pending" else "")
                ).classes("tk-secondary")
            return
        if state.status == "failed" or not state.result:
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.label(f"Check failed: {state.error or 'no result'}").classes("tk-amber")
                self.check_link("Check again")
            return
        result = state.result
        colour = {GOOD: "tk-green", BORDERLINE: "tk-amber", LOW: "tk-red"}.get(result.get("verdict"), "tk-muted")
        ui.label(result.get("message", "")).classes(f"{colour} font-medium")
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.label(
                f"Size only: blur, angle and light are not checked. Checked {when(state.finished_at)}. "
                "See the recording tips above."
            ).classes("tk-muted text-xs")
            self.check_link("Check again")

    def check_link(self, text: str) -> None:
        ui.button(text, color=None, on_click=self.request_check).props("flat dense no-caps").classes("tk-link text-xs")

    async def request_check(self) -> None:
        if self.video is None:
            return
        self.video = await query(videos.request_plate_check, self.video.id)
        ui.notify("Plate-size check requested; the worker will measure a few frames.", type="info")
        self.render_file()
        self.start_polling()

    async def start(self) -> None:
        if self.video is None:
            return
        job, created = await query(jobs.start_processing, self.video.id)
        self.job = job
        ui.notify("Queued for processing." if created else "Already queued.", type="positive" if created else "info")
        self.render_file()
        self.render_status()
        self.start_polling()

    # --- status ---------------------------------------------------------------------------------

    def render_status(self) -> None:
        self.status_card.clear()
        with self.status_card:
            ui.label("Processing Status").classes("tk-card-title")
            if self.video is None:
                ui.label("Upload or select a video to see its processing status.").classes("tk-muted mt-2")
                return
            job = self.job
            with ui.column().classes("w-full gap-2 mt-3"):
                if job is not None and job.status == "processing":
                    ui.linear_progress(job.progress, show_value=False, size="8px").classes("tk-green")
                    stage = job.stages[job.stage_index] if job.stage_index is not None else None
                    text = f"{job.progress:.0%} overall"
                    if stage and stage.total:
                        text += f" · current stage {stage.done:,} / {stage.total:,}"
                    ui.label(text).classes("tk-secondary text-sm")
                timeline(job, self.video.created_at)
                if job is not None and job.status == "completed":
                    with ui.row().classes("gap-2 mt-2"):
                        ui.button(
                            "View Analysis",
                            color=None,
                            icon="play_circle",
                            on_click=lambda: ui.navigate.to(f"/?video={self.video.id}"),
                        ).classes("tk-primary")
                        ui.button(
                            "Download Annotated Video",
                            color=None,
                            icon="download",
                            on_click=lambda: ui.navigate.to(
                                f"/api/videos/{self.video.id}/download/annotated", new_tab=True
                            ),
                        ).classes("tk-secondary")
                        ui.button(
                            "View Detections",
                            color=None,
                            icon="list",
                            on_click=lambda: ui.navigate.to(f"/history?video={self.video.id}"),
                        ).classes("tk-secondary")

    def start_polling(self) -> None:
        if self.poller is not None:
            self.poller.activate()

    def stop_polling(self) -> None:
        if self.poller is not None:
            self.poller.deactivate()

    async def poll(self) -> None:
        """Follow the job and the plate-size check while either is live; stop when neither is."""
        live = await self.poll_job()
        live = await self.poll_check() or live
        if not live:
            self.stop_polling()

    async def poll_job(self) -> bool:
        if self.job is None:
            return False
        job = await query(jobs.get_job, self.job.id)
        if job is None:
            return False
        changed = (job.status, job.stage, job.stage_done, job.progress) != (
            self.job.status,
            self.job.stage,
            self.job.stage_done,
            self.job.progress,
        )
        self.job = job
        finished = job.status in ("completed", "failed")
        if finished:
            self.video = await query(videos.get_video, self.video.id)
            self.render_file()
            await self.refresh_videos()
            ui.notify(
                "Processing completed." if job.status == "completed" else f"Processing failed: {job.error}",
                type="positive" if job.status == "completed" else "negative",
                close_button=True,
            )
        if changed or finished:
            self.render_status()
        return not finished

    async def poll_check(self) -> bool:
        if self.video is None or self.video.plate_check is None or not self.video.plate_check.live:
            return False
        fresh = await query(videos.get_video, self.video.id)
        if fresh is None or fresh.plate_check is None:
            return False
        if fresh.plate_check.status != self.video.plate_check.status:
            self.video = fresh
            self.render_file()
            if not fresh.plate_check.live:
                await self.refresh_videos()
        return fresh.plate_check.live

    # --- the list of videos ----------------------------------------------------------------------

    async def refresh_videos(self) -> None:
        listed: list[VideoSummary] = await query(videos.list_videos)
        self.videos_card.clear()
        with self.videos_card:
            ui.label("Videos").classes("tk-card-title")
            if not listed:
                ui.label("No videos yet.").classes("tk-muted mt-2")
                return
            columns = [
                {"name": "name", "label": "Video", "field": "name", "align": "left"},
                {"name": "format", "label": "Format", "field": "format", "align": "left"},
                {"name": "duration", "label": "Duration", "field": "duration", "align": "right"},
                {"name": "status", "label": "Status", "field": "status", "align": "left"},
                {"name": "plates", "label": "Plate size", "field": "plates", "align": "left"},
                {"name": "uploaded", "label": "Added", "field": "uploaded", "align": "left"},
            ]
            rows = [
                {
                    "id": v.id,
                    "name": v.name,
                    "format": f"{v.width}×{v.height} @ {v.fps_decimal:.0f} fps",
                    "duration": human_duration(v.duration_s),
                    "status": _status_text(v),
                    "plates": _check_text(v.plate_check),
                    "uploaded": when(v.created_at),
                }
                for v in listed
            ]
            table = (
                ui.table(columns=columns, rows=rows, row_key="id").classes("w-full tk-table mt-2").props("flat dense")
            )
            table.on("rowClick", lambda e: self.select(e.args[1]["id"]))
            ui.label("Click a video to select it.").classes("tk-muted text-xs mt-1")

    async def select(self, video_id: int) -> None:
        self.video = await query(videos.get_video, video_id)
        if self.video is None:
            return
        self.job = None
        self.stop_polling()
        if self.video.latest_job is not None:
            self.job = await query(jobs.get_job, self.video.latest_job.id)
            if self.job is not None and self.job.status in ("queued", "processing"):
                self.start_polling()
        if self.video.plate_check is not None and self.video.plate_check.live:
            self.start_polling()
        self.render_file()
        self.render_status()


def _status_text(video: VideoSummary) -> str:
    job = video.latest_job
    if job is None:
        return "Not processed"
    if job.status == "processing":
        return f"Processing {job.progress:.0%} of {job.stage or ''}".strip()
    return {"queued": "Queued", "completed": "Completed", "failed": "Failed"}.get(job.status, job.status)


def _check_text(state: PlateCheckState | None) -> str:
    if state is None:
        return "—"
    if state.live:
        return "Checking…"
    if state.status == "failed" or not state.result:
        return "Check failed"
    result = state.result
    words = {GOOD: "Good", BORDERLINE: "Borderline", LOW: "Too small"}
    label = words.get(result.get("verdict"), "No plates" if result.get("vehicles_seen") else "No vehicles")
    return f"{label} ({result['largest_width_px']} px)" if result.get("largest_width_px") else label


@ui.page("/upload")
async def upload_page(video: int | None = None) -> None:
    with frame("upload", "Upload & Process", "Upload an MP4 recording and run it through the pipeline"):
        page = UploadPage()
        page.build()
        if video is not None:
            await page.select(video)
