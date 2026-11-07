"""The Overview (DESIGN sections 6 to 13): the page the demo opens on.

A selector chooses which processed video the player, the processing timeline, the charts and
the detections table show; a scope switch lets the five cards count that video or all videos.
Every number comes from the service layer (`services.overview`); nothing is sampled or assumed,
and an empty database shows empty states, not placeholders.
"""

from __future__ import annotations

from nicegui import ui

from tracko_anpr.dashboard.components.detection_dialog import image_url, show_detection, status_badge
from tracko_anpr.dashboard.components.player import VideoPlayer
from tracko_anpr.dashboard.components.timeline import timeline
from tracko_anpr.dashboard.format import VEHICLE_ICONS, minutes_seconds, percent, thousands, video_time, when
from tracko_anpr.dashboard.layout import frame
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.services import overview as overview_service
from tracko_anpr.services.overview import Overview

CATEGORY_COLOURS = {"Car": "#27C443", "Motorcycle": "#FACC15", "Bus": "#F59E0B", "Truck": "#EF5B47"}
CHART_TEXT = "#858585"
CHART_GRID = "#262626"
LINE_GREEN = "#4ADE36"


class OverviewPage:
    def __init__(self, data: Overview) -> None:
        self.data = data
        self.player: VideoPlayer | None = None

    # --- building ----------------------------------------------------------------------------

    def build(self) -> None:
        self.header_row()
        self.cards_row()
        with ui.row().classes("w-full gap-4 no-wrap items-stretch tk-overview-middle"):
            with ui.element("div").classes("tk-card").style("flex: 5 1 0; min-width: 0"):
                self.player = VideoPlayer()
                self.show_video()
            with ui.element("div").classes("tk-card").style("flex: 2 1 0; min-width: 250px"):
                ui.label("Processing Status").classes("tk-card-title mb-2")
                timeline(self.data.job, self.data.selected.created_at if self.data.selected else None)
            with ui.column().classes("gap-4").style("flex: 3 1 0; min-width: 300px"):
                with ui.element("div").classes("tk-card w-full"):
                    self.category_card()
                with ui.element("div").classes("tk-card w-full"):
                    self.coverage_card()
        with ui.row().classes("w-full gap-4 no-wrap items-stretch"):
            with ui.element("div").classes("tk-card").style("flex: 3 1 0; min-width: 0"):
                self.recent_card()
            with ui.element("div").classes("tk-card").style("flex: 2 1 0; min-width: 320px"):
                self.over_time_card()

    def header_row(self) -> None:
        data = self.data
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.row().classes("items-center gap-3 no-wrap"):
                options = {video.id: video.name for video in data.processed_videos}
                selector = (
                    ui.select(
                        options,
                        value=data.selected.id if data.selected else None,
                        label="Video",
                        on_change=lambda e: ui.navigate.to(f"/?video={e.value}&scope={data.scope}"),
                    )
                    .props("outlined dense dark options-dense")
                    .style("min-width: 260px")
                )
                if not options:
                    selector.disable()
                with ui.element("div").classes("tk-segmented"):
                    for scope, label in (("video", "This video"), ("all", "All videos")):
                        button = ui.button(label, color=None, on_click=lambda _, s=scope: self.set_scope(s))
                        if scope == data.scope:
                            button.classes("active")
                        if not data.processed_videos:
                            button.disable()
            with ui.element("div").classes("tk-badge").style("border-radius: 10px; padding: 8px 16px"):
                ui.label(f"Processed: {data.overall.videos_processed} Videos")
                ui.element("span").style("width: 1px; height: 18px; background: var(--border-color)")
                ui.label(f"Last Run: {when(data.overall.last_run_at)}")

    def set_scope(self, scope: str) -> None:
        video = f"video={self.data.selected.id}&" if self.data.selected else ""
        ui.navigate.to(f"/?{video}scope={scope}")

    def cards_row(self) -> None:
        cards = self.data.cards
        average = cards.average_processing_seconds
        items = [
            ("directions_car", "Total Vehicles", thousands(cards.total_vehicles), None),
            (
                "check_box",
                "Recognized Plates",
                thousands(cards.confirmed_plates),
                percent(cards.recognition_coverage) if cards.total_vehicles else None,
            ),
            ("gps_fixed", "Unique Tracks", thousands(cards.unique_tracks), None),
            ("layers", "Videos Processed", thousands(cards.videos_processed), None),
            (
                "schedule",
                "Avg. Processing Time",
                minutes_seconds(average) if average else "—",
                "/ video" if average else None,
            ),
        ]
        with ui.element("div").classes("tk-cards w-full"):
            for icon, label, value, extra in items:
                with ui.element("div").classes("tk-card tk-metric"):
                    with ui.element("div").classes("tk-metric-icon"):
                        ui.icon(icon)
                    with ui.column().classes("gap-0"):
                        ui.label(label).classes("tk-secondary text-sm")
                        with ui.row().classes("items-baseline gap-2 no-wrap"):
                            ui.label(value).classes("tk-metric-value" + (" small" if len(value) > 8 else ""))
                            if extra:
                                ui.label(extra).classes(
                                    "tk-green text-sm" if extra.endswith("%") else "tk-secondary text-sm"
                                )
        if self.data.scope == "all":
            ui.label(
                "Cards: all processed videos (latest run of each). Charts and tables: the selected video."
            ).classes("tk-muted text-xs")
        elif cards.recognition_coverage is not None:
            ui.label("Recognized Plates shows recognition coverage, which is not a measure of accuracy.").classes(
                "tk-muted text-xs"
            )

    # --- the middle row ----------------------------------------------------------------------

    def show_video(self) -> None:
        data = self.data
        if data.selected is None or data.results is None:
            self.player.empty("No processed video yet. Upload one on the Upload & Process page.")
            return
        self.player.show(data.selected, has_annotated=bool(data.results.annotated_video_path))

    def category_card(self) -> None:
        ui.label("Vehicle Category Distribution").classes("tk-card-title")
        found = self.data.results
        counts = found.by_class if found else {name: 0 for name in CATEGORY_COLOURS}
        total = sum(counts.values())
        with ui.row().classes("w-full items-center no-wrap gap-2 mt-1"):
            if total == 0:
                with (
                    ui.element("div")
                    .classes("tk-player-empty")
                    .style("width: 170px; height: 170px; aspect-ratio: auto; border-radius: 50%")
                ):
                    ui.label("No vehicles").classes("text-xs")
            else:
                ui.echart(
                    {
                        "backgroundColor": "transparent",
                        "tooltip": {
                            "trigger": "item",
                            "backgroundColor": "#202020",
                            "borderColor": "#363636",
                            "textStyle": {"color": "#f5f5f5"},
                        },
                        "series": [
                            {
                                "type": "pie",
                                "radius": ["64%", "88%"],
                                "avoidLabelOverlap": False,
                                "label": {"show": False},
                                "itemStyle": {"borderColor": "#141414", "borderWidth": 3},
                                "data": [
                                    {"value": counts.get(name, 0), "name": name, "itemStyle": {"color": colour}}
                                    for name, colour in CATEGORY_COLOURS.items()
                                    if counts.get(name, 0)
                                ],
                            }
                        ],
                        "graphic": [
                            {
                                "type": "text",
                                "left": "center",
                                "top": "40%",
                                "style": {
                                    "text": f"{total:,}",
                                    "fill": "#f5f5f5",
                                    "fontSize": 26,
                                    "fontWeight": 700,
                                    "fontFamily": "Inter",
                                },
                            },
                            {
                                "type": "text",
                                "left": "center",
                                "top": "57%",
                                "style": {"text": "Vehicles", "fill": "#b0b0b0", "fontSize": 13, "fontFamily": "Inter"},
                            },
                        ],
                    }
                ).style("width: 180px; height: 180px; flex: 0 0 180px")
            with ui.column().classes("gap-2").style("flex: 1 1 0; min-width: 0"):
                for name, colour in CATEGORY_COLOURS.items():
                    count = counts.get(name, 0)
                    share = count / total if total else 0.0
                    with ui.row().classes("items-center no-wrap gap-2 w-full"):
                        ui.icon(VEHICLE_ICONS[name]).classes("text-xl").style(f"color: {colour}")
                        ui.label(name).classes("tk-secondary").style("flex: 1 1 0")
                        ui.label(thousands(count)).classes("font-semibold tk-mono")
                        ui.label(f"({100 * share:.1f}%)").classes("tk-muted text-sm tk-mono").style(
                            "min-width: 58px; text-align: right"
                        )

    def coverage_card(self) -> None:
        ui.label("Recognition Coverage").classes("tk-card-title")
        found = self.data.results
        summary = found.summary if found else None
        total = summary.total_vehicles if summary else 0
        confirmed = summary.confirmed_plates if summary else 0
        share = summary.recognition_coverage if summary and summary.recognition_coverage is not None else 0.0
        with ui.row().classes("w-full items-center no-wrap gap-3 mt-2"):
            ui.linear_progress(share, show_value=False, size="10px").classes("tk-green").style("flex: 1 1 0")
            ui.label(percent(share) if total else "—").classes("text-lg font-semibold tk-mono")
        ui.label(f"{confirmed:,} / {total:,} vehicles with recognized number plates").classes(
            "tk-secondary text-sm mt-1"
        )
        ui.label("Coverage, not accuracy: how many counted vehicles ended with a confirmed number.").classes(
            "tk-muted text-xs"
        )

    # --- the bottom row ----------------------------------------------------------------------

    def recent_card(self) -> None:
        data = self.data
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Recent Detections").classes("tk-card-title")
            target = f"/history?video={data.selected.id}" if data.selected else "/history"
            ui.button("View All", color=None, icon="arrow_forward", on_click=lambda: ui.navigate.to(target)).props(
                "flat"
            ).classes("tk-link")
        if not data.recent:
            ui.label("No detections yet." if data.selected else "No processed video selected.").classes("tk-muted mt-2")
            return
        with ui.element("div").classes("tk-table-wrap w-full mt-2"), ui.element("table").classes("tk-html-table"):
            with ui.element("thead"), ui.element("tr"):
                for heading in (
                    "Time (hh:mm:ss)",
                    "Track ID",
                    "Vehicle",
                    "Registration Number",
                    "Confidence",
                    "Validation",
                    "Plate Image",
                ):
                    with ui.element("th"):
                        ui.label(heading)
            with ui.element("tbody"):
                for row in data.recent:
                    d = row.detection
                    tr = ui.element("tr").classes("tk-row")
                    tr.on("click", lambda _, pk=d.track_pk, t=d.first_seen_s: self.row_clicked(pk, t))
                    with tr:
                        with ui.element("td"):
                            ui.label(video_time(d.first_seen_s)).classes("tk-mono")
                        with ui.element("td"):
                            ui.label(f"T{d.track_id}")
                        with ui.element("td"), ui.row().classes("items-center gap-2 no-wrap"):
                            ui.icon(VEHICLE_ICONS.get(d.vehicle_type, "directions_car")).classes("text-lg tk-secondary")
                            ui.label(d.vehicle_type)
                        with ui.element("td"):
                            ui.label(d.registration_number or "—").classes("font-semibold tk-mono")
                        with ui.element("td"):
                            ui.label(f"{d.confidence:.2f}" if d.status != "not_detected" else "—").classes("tk-mono")
                        with ui.element("td"):
                            status_badge(d.status)
                        with ui.element("td"):
                            if image_url(d.plate_crop_path):
                                ui.image(image_url(d.plate_crop_path)).classes("tk-plate-thumb")
                            else:
                                ui.label("—").classes("tk-muted")
        ui.label("Click a row to jump the video to that moment and see the details.").classes("tk-muted text-xs mt-1")

    async def row_clicked(self, track_pk: int, seconds: float) -> None:
        if self.player is not None:
            self.player.seek(max(0.0, seconds - 0.5), play=False)
        await show_detection(track_pk)

    def over_time_card(self) -> None:
        ui.label("Detections Over Time").classes("tk-card-title")
        found = self.data.results
        buckets = found.detections_over_time if found else []
        if not buckets or sum(count for _, count in buckets) == 0:
            with ui.element("div").classes("tk-player-empty w-full mt-2").style("aspect-ratio: auto; height: 240px"):
                ui.label("No vehicles to plot")
            return
        labels = [f"{start // 60:02d}:{start % 60:02d}" for start, _ in buckets]
        values = [count for _, count in buckets]
        ui.echart(
            {
                "backgroundColor": "transparent",
                "grid": {"left": 44, "right": 16, "top": 20, "bottom": 44},
                "tooltip": {
                    "trigger": "axis",
                    "backgroundColor": "#202020",
                    "borderColor": "#363636",
                    "textStyle": {"color": "#f5f5f5"},
                    "axisPointer": {"lineStyle": {"color": "#4a4a4a"}},
                },
                "xAxis": {
                    "type": "category",
                    "data": labels,
                    "name": "Video Time (mm:ss)",
                    "nameLocation": "middle",
                    "nameGap": 28,
                    "nameTextStyle": {"color": CHART_TEXT},
                    "axisLabel": {"color": CHART_TEXT},
                    "axisLine": {"lineStyle": {"color": CHART_GRID}},
                    "axisTick": {"show": False},
                },  # fmt: skip
                "yAxis": {
                    "type": "value",
                    "minInterval": 1,
                    "name": "Vehicles",
                    "nameLocation": "middle",
                    "nameGap": 30,
                    "nameTextStyle": {"color": CHART_TEXT},
                    "axisLabel": {"color": CHART_TEXT},
                    "splitLine": {"lineStyle": {"color": CHART_GRID}},
                },  # fmt: skip
                "series": [
                    {
                        "type": "line",
                        "data": values,
                        "smooth": 0.25,
                        "symbol": "circle",
                        "symbolSize": 5,
                        "lineStyle": {"color": LINE_GREEN, "width": 2},
                        "itemStyle": {"color": LINE_GREEN},
                        "areaStyle": {"color": "rgba(74, 222, 54, 0.12)"},
                    }  # fmt: skip
                ],
            }
        ).classes("w-full").style("height: 250px")
        ui.label(
            "New vehicles per 10-second bucket, each counted once where first seen; they add up to Total Vehicles"
        ).classes("tk-muted text-xs")


@ui.page("/")
async def overview_page(video: int | None = None, scope: str = "video") -> None:
    data: Overview = await query(overview_service.overview, video, scope)
    with frame("overview", "Overview", "Vehicle Detection, Tracking and Number Plate Recognition from Uploaded Videos"):
        OverviewPage(data).build()
