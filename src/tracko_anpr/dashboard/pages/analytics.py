"""Analytics (DESIGN section 15): distribution, coverage, activity, timing, confidence, validated vs uncertain.

For one video or across all of them; every figure comes from `services.analytics`.
"""

from __future__ import annotations

from nicegui import ui

from tracko_anpr.dashboard.format import VEHICLE_ICONS, human_duration, percent, thousands
from tracko_anpr.dashboard.layout import frame
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.db import metrics
from tracko_anpr.services import analytics as analytics_service
from tracko_anpr.services import videos
from tracko_anpr.services.analytics import Analytics

CATEGORY_COLOURS = {"Car": "#27C443", "Motorcycle": "#FACC15", "Bus": "#F59E0B", "Truck": "#EF5B47"}
STATUS_COLOURS = {"confirmed": "#36D428", "unconfirmed": "#FACC15", "not_detected": "#6b6b6b"}
TEXT, GRID, GREEN = "#858585", "#262626", "#4ADE36"
TOOLTIP = {"backgroundColor": "#202020", "borderColor": "#363636", "textStyle": {"color": "#f5f5f5"}}


def _axis(name: str = "", rotate: int = 0) -> dict:
    return {
        "name": name, "nameLocation": "middle", "nameGap": 30, "nameTextStyle": {"color": TEXT},
        "axisLabel": {"color": TEXT, "rotate": rotate}, "axisLine": {"lineStyle": {"color": GRID}},
        "axisTick": {"show": False}, "splitLine": {"lineStyle": {"color": GRID}},
    }  # fmt: skip


def bar_chart(labels: list[str], values: list[float], colour: str | list[str], y_name: str, height: int = 240) -> None:
    data = (
        values
        if isinstance(colour, str)
        else [{"value": v, "itemStyle": {"color": c}} for v, c in zip(values, colour, strict=True)]
    )
    ui.echart(
        {
            "backgroundColor": "transparent",
            "grid": {"left": 48, "right": 16, "top": 16, "bottom": 56},
            "tooltip": {"trigger": "axis", **TOOLTIP},
            "xAxis": {"type": "category", "data": labels, **_axis(rotate=20 if len(labels) > 6 else 0)},
            "yAxis": {
                "type": "value",
                "minInterval": 1 if all(float(v).is_integer() for v in values) else None,
                **_axis(y_name),
            },
            "series": [
                {
                    "type": "bar",
                    "data": data,
                    "barMaxWidth": 46,
                    "itemStyle": {"color": colour if isinstance(colour, str) else None, "borderRadius": [4, 4, 0, 0]},
                }
            ],
        }
    ).classes("w-full").style(f"height: {height}px")


def empty(message: str, height: int = 200) -> None:
    with ui.element("div").classes("tk-player-empty w-full").style(f"aspect-ratio: auto; height: {height}px"):
        ui.label(message)


class AnalyticsPage:
    def __init__(self, data: Analytics, options: dict, vehicles_per_video: dict[int, int]) -> None:
        self.data, self.options = data, options
        self.vehicles_per_video = vehicles_per_video

    def build(self) -> None:
        data = self.data
        with ui.row().classes("w-full items-center gap-3 no-wrap"):
            ui.select(
                self.options, value=data.video_id, label="Scope",
                on_change=lambda e: ui.navigate.to("/analytics" if e.value is None else f"/analytics?video={e.value}"),
            ).props("outlined dense dark options-dense").style("min-width: 260px")  # fmt: skip
            ui.label(
                "All figures are measured over each video's latest completed run. Coverage and confidence are not "
                "accuracy."
            ).classes("tk-muted text-sm")
        if data.summary.total_vehicles == 0 and not data.runs:
            with ui.element("div").classes("tk-card w-full"):
                ui.label("Nothing processed yet. Upload a video on the Upload & Process page.").classes("tk-muted")
            return
        with ui.row().classes("w-full gap-4 no-wrap items-stretch"):
            with ui.element("div").classes("tk-card").style("flex: 1 1 0; min-width: 0"):
                self.categories()
            with ui.element("div").classes("tk-card").style("flex: 1 1 0; min-width: 0"):
                self.validation()
            with ui.element("div").classes("tk-card").style("flex: 1 1 0; min-width: 0"):
                self.coverage()
        with ui.row().classes("w-full gap-4 no-wrap items-stretch"):
            with ui.element("div").classes("tk-card").style("flex: 1 1 0; min-width: 0"):
                self.activity()
            with ui.element("div").classes("tk-card").style("flex: 1 1 0; min-width: 0"):
                self.confidence()
        with ui.element("div").classes("tk-card w-full"):
            self.processing()

    def categories(self) -> None:
        ui.label("Vehicle Category Distribution").classes("tk-card-title")
        counts = self.data.by_class
        total = sum(counts.values())
        if not total:
            empty("No vehicles")
            return
        ui.echart(
            {
                "backgroundColor": "transparent",
                "tooltip": {"trigger": "item", **TOOLTIP},
                "series": [
                    {
                        "type": "pie",
                        "radius": ["55%", "82%"],
                        "label": {"show": False},
                        "itemStyle": {"borderColor": "#141414", "borderWidth": 3},
                        "data": [
                            {"value": n, "name": k, "itemStyle": {"color": CATEGORY_COLOURS[k]}}
                            for k, n in counts.items()
                            if n
                        ],
                    }
                ],  # fmt: skip
                "graphic": [
                    {
                        "type": "text",
                        "left": "center",
                        "top": "44%",
                        "style": {
                            "text": f"{total:,}",
                            "fill": "#f5f5f5",
                            "fontSize": 24,
                            "fontWeight": 700,
                            "fontFamily": "Inter",
                        },
                    },
                    {
                        "type": "text",
                        "left": "center",
                        "top": "58%",
                        "style": {"text": "Vehicles", "fill": "#b0b0b0", "fontSize": 12, "fontFamily": "Inter"},
                    },
                ],  # fmt: skip
            }
        ).classes("w-full").style("height: 200px")
        for name, colour in CATEGORY_COLOURS.items():
            with ui.row().classes("items-center no-wrap gap-2 w-full"):
                ui.icon(VEHICLE_ICONS[name]).classes("text-lg").style(f"color: {colour}")
                ui.label(name).classes("tk-secondary").style("flex: 1 1 0")
                ui.label(thousands(counts.get(name, 0))).classes("font-semibold tk-mono")
                ui.label(f"({percent(counts.get(name, 0) / total)})").classes("tk-muted text-sm tk-mono").style(
                    "min-width: 58px; text-align: right"
                )

    def validation(self) -> None:
        ui.label("Validated vs Uncertain Registrations").classes("tk-card-title")
        counts = self.data.by_status
        total = sum(counts.values())
        if not total:
            empty("No vehicles")
            return
        labels = {"confirmed": "Confirmed", "unconfirmed": "Unconfirmed", "not_detected": "No plate found"}
        bar_chart(
            [labels[k] for k in labels],
            [counts.get(k, 0) for k in labels],
            [STATUS_COLOURS[k] for k in labels],
            "Vehicles",
            200,
        )
        for key, label in labels.items():
            with ui.row().classes("items-center no-wrap gap-2 w-full"):
                ui.element("span").classes("tk-dot").style(f"background: {STATUS_COLOURS[key]}")
                ui.label(label).classes("tk-secondary").style("flex: 1 1 0")
                ui.label(thousands(counts.get(key, 0))).classes("font-semibold tk-mono")
                ui.label(f"({percent(counts.get(key, 0) / total)})").classes("tk-muted text-sm tk-mono").style(
                    "min-width: 58px; text-align: right"
                )

    def coverage(self) -> None:
        ui.label("Recognition Coverage").classes("tk-card-title")
        s = self.data.summary
        share = s.recognition_coverage or 0.0
        with ui.row().classes("w-full items-center no-wrap gap-3 mt-3"):
            ui.linear_progress(share, show_value=False, size="12px").classes("tk-green").style("flex: 1 1 0")
            ui.label(percent(share) if s.total_vehicles else "—").classes("text-2xl font-semibold tk-mono")
        ui.label(
            f"{s.confirmed_plates:,} / {s.total_vehicles:,} counted vehicles ended with a confirmed number"
        ).classes("tk-secondary text-sm mt-2")
        ui.label(
            "Coverage, not accuracy. Most vehicles that end without a number are seen from the side, cut off by "
            "the frame, or too far away for the plate to be read (under about 60 px wide)."
        ).classes("tk-muted text-xs mt-2")
        with ui.element("div").classes("tk-kv mt-4"):
            ui.label("Unique tracks").classes("k")
            ui.label(thousands(s.unique_tracks)).classes("v")
            ui.label("Counted vehicles").classes("k")
            ui.label(thousands(s.total_vehicles)).classes("v")
            ui.label("Videos").classes("k")
            ui.label(thousands(s.videos_processed)).classes("v")

    def activity(self) -> None:
        data = self.data
        if data.video_id is not None:
            ui.label("Detection Activity").classes("tk-card-title")
            buckets = data.detections_over_time
            if not buckets or not sum(c for _, c in buckets):
                empty("No vehicles to plot")
                return
            ui.echart(
                {
                    "backgroundColor": "transparent",
                    "grid": {"left": 44, "right": 16, "top": 16, "bottom": 44},
                    "tooltip": {"trigger": "axis", **TOOLTIP},
                    "xAxis": {
                        "type": "category",
                        "data": [f"{s // 60:02d}:{s % 60:02d}" for s, _ in buckets],
                        **_axis("Video time (mm:ss)"),
                    },
                    "yAxis": {"type": "value", "minInterval": 1, **_axis("New vehicles")},
                    "series": [
                        {
                            "type": "line",
                            "data": [c for _, c in buckets],
                            "smooth": 0.25,
                            "symbol": "circle",
                            "symbolSize": 5,
                            "lineStyle": {"color": GREEN, "width": 2},
                            "itemStyle": {"color": GREEN},
                            "areaStyle": {"color": "rgba(74, 222, 54, 0.12)"},
                        }
                    ],  # fmt: skip
                }
            ).classes("w-full").style("height: 240px")
            ui.label("New vehicles per 10-second bucket; the buckets add up to the counted vehicles.").classes(
                "tk-muted text-xs"
            )
        else:
            ui.label("Detection Activity by Video").classes("tk-card-title")
            runs = data.runs
            if not runs:
                empty("No processed videos")
                return
            vehicles = [self.vehicles_per_video.get(run.video_id, 0) for run in runs]
            bar_chart([run.video_name for run in runs], vehicles, GREEN, "Counted vehicles")
            ui.label("Counted vehicles in each video's latest run.").classes("tk-muted text-xs")

    def confidence(self) -> None:
        ui.label("Recognition Confidence Distribution").classes("tk-card-title")
        bands = self.data.confidence_distribution
        if not sum(n for _, n in bands):
            empty("No confirmed numbers yet")
            return
        bar_chart([label for label, _ in bands], [n for _, n in bands], GREEN, "Confirmed numbers")
        ui.label(
            "Confidence of confirmed numbers (average of the agreeing readings). Confidence is the reader's own "
            "score, not a measure of accuracy."
        ).classes("tk-muted text-xs")

    def processing(self) -> None:
        data = self.data
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Video Processing Duration and Inference Latency").classes("tk-card-title")
            parts = []
            if data.average_detect_track_ms_per_frame is not None:
                parts.append(f"detection and tracking {data.average_detect_track_ms_per_frame:.1f} ms per frame")
            if data.average_ocr_ms_per_plate is not None:
                parts.append(f"plate reading {data.average_ocr_ms_per_plate:.0f} ms per plate")
            if parts:
                ui.label("Average inference latency: " + ", ".join(parts)).classes("tk-secondary text-sm")
        runs = data.runs
        if not runs:
            empty("No processed videos")
            return
        with ui.row().classes("w-full gap-4 no-wrap items-start mt-2"):
            with ui.element("div").style("flex: 1 1 0; min-width: 0"):
                bar_chart(
                    [r.video_name for r in runs], [round(r.processing_seconds / 60, 2) for r in runs], GREEN, "Minutes"
                )
                ui.label("Wall-clock processing time of each video's latest run, in minutes.").classes(
                    "tk-muted text-xs"
                )
            with (
                ui.element("div").classes("tk-table-wrap").style("flex: 1 1 0; min-width: 0"),
                ui.element("table").classes("tk-html-table"),
            ):
                with ui.element("thead"), ui.element("tr"):
                    for heading in ("Video", "Length", "Processing", "Speed", "Frames", "ms / frame", "ms / plate"):
                        with ui.element("th"):
                            ui.label(heading)
                with ui.element("tbody"):
                    for r in runs:
                        with ui.element("tr"):
                            latency = r.detect_track_ms_per_frame
                            values = (
                                r.video_name,
                                human_duration(r.duration_s),
                                human_duration(r.processing_seconds),
                                f"{r.times_real_time:.2f}× real time" if r.times_real_time else "—",
                                thousands(r.frames),
                                "—" if latency is None else f"{latency:.1f}",
                                "—" if r.ocr_ms_per_plate is None else f"{r.ocr_ms_per_plate:.0f}",
                            )
                            for value in values:
                                with ui.element("td"):
                                    ui.label(value).classes("tk-mono")


def _load(session, video_id: int | None):
    data = analytics_service.analytics(session, video_id)
    listed = videos.list_videos(session)
    options = {None: "All videos"} | {v.id: v.name for v in listed if v.completed_job_id is not None}
    per_video = {v.id: metrics.summary(session, v.id).total_vehicles for v in listed if v.completed_job_id is not None}
    return data, options, per_video


@ui.page("/analytics")
async def analytics_page(video: int | None = None) -> None:
    data, options, per_video = await query(_load, video)
    with frame("analytics", "Analytics", "Category distribution, coverage, activity, timing and confidence"):
        AnalyticsPage(data, options, per_video).build()
