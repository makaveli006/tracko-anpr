"""Mounting the NiceGUI dashboard on the FastAPI app, so one process serves both.

NiceGUI keeps each browser session's state in memory, which is why the dashboard and the
API share one process (ARCHITECTURE.md, "Web Process"). Pages live in `dashboard/pages/`;
importing a page module registers its routes. Pages must never query the database or read
files themselves: they call the service functions in `tracko_anpr.services` through
`dashboard.runtime.query`, exactly as the API routes do.

Static files (the theme stylesheet and the Inter font) are served from this package at
/dashboard-static, so nothing is fetched from the internet at run time.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

STATIC_DIR = Path(__file__).parent / "static"
STATIC_URL = "/dashboard-static"


def mount_dashboard(app: FastAPI) -> None:
    from nicegui import app as nicegui_app
    from nicegui import ui

    from tracko_anpr.dashboard.runtime import runtime

    runtime.configure(app.state.settings, app.state.engine, app.state.session_factory)
    nicegui_app.add_static_files(STATIC_URL, STATIC_DIR)

    # Importing the page modules registers their routes.
    from tracko_anpr.dashboard.pages import placeholders, upload  # noqa: F401

    ui.run_with(
        app,
        title="Vehicle ANPR POC",
        favicon=str(STATIC_DIR / "favicon.svg"),
        dark=True,
        storage_secret=None,
        reconnect_timeout=10.0,
    )
