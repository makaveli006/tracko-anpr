"""The "System Ready" panel at the bottom of the sidebar (DESIGN section 5).

It shows the real readiness from `services.readiness`, refreshed every few seconds, and turns
amber with the failing checks named when a service is missing: never a false green.
"""

from __future__ import annotations

from nicegui import ui

from tracko_anpr.dashboard.runtime import query, runtime
from tracko_anpr.services import readiness
from tracko_anpr.services.readiness import SystemStatus

REFRESH_SECONDS = 5.0
CHECKING = "Checking…"


def _status(session) -> SystemStatus:
    return readiness.system_status(runtime.settings, runtime.engine, session)


def status_panel() -> None:
    panel = ui.element("div").classes("tk-status")

    def render(status: SystemStatus | None, error: str | None = None) -> None:
        panel.clear()
        with panel:
            if status is None:
                checking = error == CHECKING
                with ui.element("div").classes("tk-status-title"):
                    if checking:
                        ui.image("/dashboard-static/logo/mark.png").classes("tk-status-mark").props("no-spinner")
                    else:
                        ui.element("span").classes("tk-dot red")
                    ui.label("System Status" if checking else "Status unavailable")
                ui.label(error or "").classes("tk-muted" if checking else "tk-status-problem")
                return
            with ui.element("div").classes("tk-status-title"):
                ui.element("span").classes("tk-dot" if status.ready else "tk-dot amber")
                ui.label("System Ready" if status.ready else "Attention needed")
            for key, value in (("GPU", status.gpu), ("Models", status.models), ("OCR", status.ocr)):
                with ui.element("div").classes("tk-status-row"):
                    ui.label(key).classes("k")
                    ui.label(": " + value).classes("v")
            for check in status.checks:
                if not check.ok and check.name != "gpu":
                    ui.label(f"{check.name}: {check.detail}").classes("tk-status-problem")

    async def refresh() -> None:
        try:
            status = await query(_status)
        except Exception as error:  # the database is down: say so instead of crashing the page
            render(None, f"Database not reachable ({type(error).__name__}).")
            return
        render(status)

    render(None, CHECKING)
    ui.timer(0.1, refresh, once=True)
    ui.timer(REFRESH_SECONDS, refresh)
