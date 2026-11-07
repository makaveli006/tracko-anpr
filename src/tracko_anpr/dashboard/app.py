"""Mounting the NiceGUI dashboard on the FastAPI app, so one process serves both.

NiceGUI keeps each browser session's state in memory, which is why the dashboard and the
API share one process (ARCHITECTURE.md, "Web Process"). The pages are built in Phases 11 to
13; until then `/` shows a plain placeholder with the API's status, so `tracko-anpr web` can
be started and checked end to end.

Pages must never query the database or read files themselves: they call the service
functions in `tracko_anpr.services`, exactly as the API routes do.
"""

from __future__ import annotations

from fastapi import FastAPI


def mount_dashboard(app: FastAPI) -> None:
    from nicegui import ui

    @ui.page("/")
    def placeholder() -> None:
        ui.dark_mode(True)
        ui.query("body").style("background-color: #0a0a0a; color: #e5e5e5")
        with ui.column().classes("p-8 gap-2"):
            ui.label("tracko-anpr").classes("text-2xl font-semibold")
            ui.label("The dashboard is built in the next phases. The API is up:")
            ui.link("API documentation", "/api/docs").style("color: #4ADE36")
            ui.link("System status", "/api/system/status").style("color: #4ADE36")

    ui.run_with(app, title="tracko-anpr", favicon="🚗", dark=True, storage_secret=None)
