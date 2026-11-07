"""Detection History (DESIGN section 15): every counted vehicle across all videos, searchable.

Filters (video, validation state, vehicle type, number search), sortable columns, paging and a
CSV export of exactly the rows shown. A row opens the details; from there "Open in Video
Analysis" lands on the player at that moment.
"""

from __future__ import annotations

from urllib.parse import urlencode

from nicegui import ui

from tracko_anpr.dashboard.components.detection_dialog import show_detection
from tracko_anpr.dashboard.components.detections_table import detections_table
from tracko_anpr.dashboard.layout import frame
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.services import results, videos
from tracko_anpr.services.results import DetectionRow, HistoryPage

PAGE_SIZE = 25
STATUSES = {
    None: "All validation states",
    "confirmed": "Confirmed",
    "unconfirmed": "Unconfirmed",
    "not_detected": "Not detected",
}
TYPES = {None: "All vehicle types", "Car": "Car", "Motorcycle": "Motorcycle", "Bus": "Bus", "Truck": "Truck"}


class HistoryView:
    def __init__(
        self,
        video: int | None,
        status: str | None,
        vehicle_type: str | None,
        search: str,
        sort: str,
        desc: bool,
        offset: int,
    ) -> None:
        self.video, self.status, self.vehicle_type, self.search = video, status, vehicle_type, search
        self.sort, self.desc, self.offset = sort, desc, offset
        self.page: HistoryPage | None = None
        self.options: dict[int | None, str] = {None: "All videos"}

    def url(self, **changes) -> str:
        values = {"video": self.video, "status": self.status, "type": self.vehicle_type, "q": self.search or None,
                  "sort": self.sort, "desc": int(self.desc), "offset": self.offset}  # fmt: skip
        values.update(changes)
        return "/history?" + urlencode({k: v for k, v in values.items() if v not in (None, "")})

    def export_url(self) -> str:
        values = {
            "video_id": self.video,
            "status": self.status,
            "vehicle_type": self.vehicle_type,
            "search": self.search or None,
        }
        return "/api/detections/export.csv?" + urlencode({k: v for k, v in values.items() if v not in (None, "")})

    async def load(self) -> None:
        listed = await query(videos.list_videos)
        self.options.update({v.id: v.name for v in listed if v.completed_job_id is not None})
        self.page = await query(
            results.detection_history, self.video, self.status, self.vehicle_type, self.search or None,
            self.sort, self.desc, self.offset, PAGE_SIZE,
        )  # fmt: skip

    def build(self) -> None:
        with ui.element("div").classes("tk-card w-full"):
            with ui.row().classes("w-full items-end gap-3 no-wrap"):
                ui.select(
                    self.options,
                    value=self.video,
                    label="Video",
                    on_change=lambda e: ui.navigate.to(self.url(video=e.value, offset=0)),
                ).props("outlined dense dark options-dense").style("min-width: 220px")
                ui.select(
                    STATUSES,
                    value=self.status,
                    label="Validation",
                    on_change=lambda e: ui.navigate.to(self.url(status=e.value, offset=0)),
                ).props("outlined dense dark options-dense").style("min-width: 200px")
                ui.select(
                    TYPES,
                    value=self.vehicle_type,
                    label="Vehicle type",
                    on_change=lambda e: ui.navigate.to(self.url(type=e.value, offset=0)),
                ).props("outlined dense dark options-dense").style("min-width: 180px")
                search = (
                    ui.input("Registration number", value=self.search, placeholder="e.g. KL07")
                    .props("outlined dense dark clearable")
                    .style("min-width: 220px")
                )
                search.on("keydown.enter", lambda: ui.navigate.to(self.url(q=search.value or None, offset=0)))
                ui.button(
                    "Search",
                    color=None,
                    icon="search",
                    on_click=lambda: ui.navigate.to(self.url(q=search.value or None, offset=0)),
                ).classes("tk-secondary")
                ui.element("div").style("flex: 1 1 0")
                ui.button(
                    "Export CSV",
                    color=None,
                    icon="download",
                    on_click=lambda: ui.navigate.to(self.export_url(), new_tab=True),
                ).classes("tk-primary")
            page = self.page
            total = page.total if page else 0
            first = page.offset + 1 if total else 0
            last = min(page.offset + len(page.rows), total) if page else 0
            with ui.row().classes("w-full items-center justify-between no-wrap mt-3"):
                ui.label(f"{first:,}–{last:,} of {total:,} counted vehicles").classes("tk-secondary text-sm")
                with ui.row().classes("gap-2 no-wrap"):
                    previous = (
                        ui.button(
                            "Previous",
                            color=None,
                            icon="chevron_left",
                            on_click=lambda: ui.navigate.to(self.url(offset=max(0, self.offset - PAGE_SIZE))),
                        )
                        .classes("tk-secondary")
                        .props("dense")
                    )
                    following = (
                        ui.button(
                            "Next",
                            color=None,
                            on_click=lambda: ui.navigate.to(self.url(offset=self.offset + PAGE_SIZE)),
                        )
                        .classes("tk-secondary")
                        .props("dense")
                    )
                    if self.offset == 0:
                        previous.disable()
                    if last >= total:
                        following.disable()
            if page is None or not page.rows:
                ui.label("No detections match." if total == 0 else "Nothing on this page.").classes("tk-muted mt-3")
                return
            with ui.element("div").classes("w-full mt-2"):
                detections_table(
                    page.rows,
                    (
                        "time",
                        "video",
                        "track",
                        "vehicle_type",
                        "registration_number",
                        "confidence",
                        "status",
                        "registry",
                        "plate",
                    ),
                    self.row_clicked,
                    sort=self.sort,
                    descending=self.desc,
                    on_sort=self.sorted_by,
                )
            ui.label(
                "Click a row for the details and to open it in Video Analysis. Confidence is not accuracy; the "
                "registry is fictional."
            ).classes("tk-muted text-xs mt-1")

    def sorted_by(self, column: str) -> None:
        descending = not self.desc if column == self.sort else column in ("time", "confidence")
        ui.navigate.to(self.url(sort=column, desc=int(descending), offset=0))

    async def row_clicked(self, row: DetectionRow) -> None:
        d = row.detection
        await show_detection(
            d.track_pk, open_in_analysis=f"/analysis?video={d.video_id}&t={max(0.0, d.first_seen_s - 0.5):.2f}"
        )


@ui.page("/history")
async def history_page(
    video: int | None = None, status: str | None = None, type: str | None = None, q: str = "",
    sort: str = "time", desc: int = 1, offset: int = 0,
) -> None:  # fmt: skip
    view = HistoryView(video, status or None, type or None, q, sort, bool(desc), max(0, offset))
    await view.load()
    with frame("history", "Detection History", "Every recognised number plate, across all processed videos"):
        view.build()
