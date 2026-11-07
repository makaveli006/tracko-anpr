"""The video player (DESIGN section 8): original or annotated footage, position kept when switching.

The browser's own controls give play/pause, the seek bar, the time, volume, speed and
fullscreen. The segmented control above the player switches between the original upload and
the annotated video; the JavaScript keeps the current time and the playing state across the
switch. `seek()` lets a table row jump the video to a moment.
"""

from __future__ import annotations

from nicegui import ui

from tracko_anpr.services.videos import VideoSummary


def original_url(video_id: int) -> str:
    return f"/api/videos/{video_id}/original"


def annotated_url(video_id: int) -> str:
    return f"/api/videos/{video_id}/annotated"


class VideoPlayer:
    """A player with an Original / Annotated switch. Call `show()` with a video, or `empty()`."""

    def __init__(self) -> None:
        self.video: VideoSummary | None = None
        self.mode = "annotated"
        self.sources: dict[str, str] = {}
        with ui.column().classes("w-full gap-3"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label("Video Analysis").classes("tk-card-title")
                with ui.element("div").classes("tk-segmented"):
                    self.original_button = ui.button("Original Video", on_click=lambda: self.switch("original"))
                    self.annotated_button = ui.button("Annotated Video", on_click=lambda: self.switch("annotated"))
            self.frame = ui.element("div").classes("w-full tk-player")
            self.element: ui.video | None = None
        self.empty()

    # --- what is shown ---------------------------------------------------------------------

    def empty(self, message: str = "No video selected") -> None:
        self.video = None
        self.sources = {}
        self.frame.clear()
        self.frame.classes(remove="tk-player")
        with self.frame, ui.element("div").classes("tk-player-empty w-full"):
            ui.label(message)
        self.element = None
        self._style_buttons()

    def show(self, video: VideoSummary, has_annotated: bool) -> None:
        """Play this video: the annotated copy when it exists, the original otherwise."""
        self.video = video
        self.sources = {"original": original_url(video.id)}
        if has_annotated:
            self.sources["annotated"] = annotated_url(video.id)
        self.mode = "annotated" if has_annotated else "original"
        self.frame.clear()
        self.frame.classes(add="tk-player")
        with self.frame:
            self.element = ui.video(self.sources[self.mode], controls=True).props("preload=metadata playsinline")
        self._style_buttons()

    def switch(self, mode: str) -> None:
        """Change footage without losing the place: same time, still playing if it was playing."""
        if self.element is None or mode == self.mode or mode not in self.sources:
            return
        self.mode = mode
        self._style_buttons()
        ui.run_javascript(
            f"""
            const video = getHtmlElement({self.element.id});
            const time = video.currentTime, playing = !video.paused && !video.ended, rate = video.playbackRate;
            video.src = {self.sources[mode]!r};
            video.addEventListener('loadedmetadata', () => {{
                video.currentTime = time; video.playbackRate = rate; if (playing) video.play();
            }}, {{once: true}});
            video.load();
            """
        )

    def seek(self, seconds: float, play: bool = True) -> None:
        """Jump to a moment in the video (a table row was clicked)."""
        if self.element is None:
            return
        action = "video.play();" if play else ""
        ui.run_javascript(
            f"const video = getHtmlElement({self.element.id}); video.currentTime = {float(seconds)}; {action}"
        )

    def _style_buttons(self) -> None:
        for mode, button in (("original", self.original_button), ("annotated", self.annotated_button)):
            active = self.element is not None and mode == self.mode
            button.classes(add="active" if active else None, remove=None if active else "active")
            button.set_enabled(mode in self.sources)
