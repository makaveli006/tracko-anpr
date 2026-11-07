"""Settings (DESIGN section 15): model, processing, tracking, recognition and storage configuration.

The pipeline's settings are frozen (Phase 7): changing one would mean processing every demo
video again. So this page shows the real values the pipeline runs with, grouped as the design
asks, and says so. Each job keeps its own snapshot in the database.
"""

from __future__ import annotations

from nicegui import ui

from tracko_anpr.dashboard.layout import frame
from tracko_anpr.dashboard.runtime import query, runtime
from tracko_anpr.services import app_settings

GROUP_ORDER = (
    "Model configuration",
    "Processing resolution",
    "Tracking configuration",
    "Detection thresholds",
    "Recognition thresholds",
    "Video output",
    "Storage",
)


def _load(session):
    return app_settings.current(session, runtime.settings)


@ui.page("/settings")
async def settings_page() -> None:
    items = await query(_load)
    with frame("settings", "Settings", "Model, tracking and recognition configuration"):
        with ui.element("div").classes("tk-banner amber w-full"):
            ui.icon("lock")
            ui.label(
                "These settings were frozen on 2026-11-06 after the acceptance run. Changing one means processing "
                "every "
                "demo video again, so they are shown here as they run; every job records the settings it used."
            ).classes("text-sm font-normal")
        groups: dict[str, list] = {}
        for item in items:
            groups.setdefault(item.group, []).append(item)
        with ui.element("div").classes("tk-settings-grid w-full"):
            for group in GROUP_ORDER:
                rows = groups.get(group, [])
                if not rows:
                    continue
                with ui.element("div").classes("tk-card"):
                    ui.label(group).classes("tk-card-title")
                    with ui.element("div").classes("tk-kv mt-3"):
                        for item in rows:
                            ui.label(item.label).classes("k")
                            with ui.column().classes("v gap-0"):
                                value = f"{item.value} {item.unit}".strip() if item.unit else str(item.value)
                                with ui.row().classes("items-baseline gap-2 no-wrap"):
                                    ui.label(value).classes("tk-mono")
                                    if item.value != item.default:
                                        ui.label(f"(stored; the pipeline runs with {item.default})").classes(
                                            "tk-amber text-xs"
                                        )
                                if item.description:
                                    ui.label(item.description).classes("tk-muted text-xs")
