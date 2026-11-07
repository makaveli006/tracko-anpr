"""Pages not built yet, so every navigation item leads somewhere inside the frame.

Each one says which phase builds it. They show nothing invented: no sample numbers, no
mock tables (DESIGN section 7: sample numbers only in clearly labelled demonstration mode).
"""

from __future__ import annotations

from nicegui import ui

from tracko_anpr.dashboard.layout import frame

PENDING = (
    ("/", "overview", "Overview", "Vehicle Detection, Tracking and Number Plate Recognition from Uploaded Videos", 12),
    ("/analysis", "analysis", "Video Analysis", "Original and annotated playback with track details", 13),
    ("/history", "history", "Detection History", "Every recognised number plate, across all videos", 13),
    ("/registry", "registry", "Demo Registry", "Demonstration Data Only — fictional vehicle records", 13),
    ("/analytics", "analytics", "Analytics", "Category distribution, coverage, timing", 13),
    ("/settings", "settings", "Settings", "Model, tracking and recognition configuration", 13),
)


def _register(path: str, key: str, title: str, subtitle: str, phase: int) -> None:
    @ui.page(path)
    def page(video: int | None = None) -> None:
        with frame(key, title, subtitle), ui.element("div").classes("tk-card w-full"):
            ui.label(f"This page is built in Phase {phase}.").classes("tk-secondary")
            ui.label("Until then, the Upload & Process page and the API are the way in.").classes("tk-muted text-sm")
            ui.link("Go to Upload & Process", "/upload").classes("mt-2 inline-block")


for _path, _key, _title, _subtitle, _phase in PENDING:
    _register(_path, _key, _title, _subtitle, _phase)
