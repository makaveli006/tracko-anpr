"""The frame every page sits in: theme, header, sidebar with the status panel, content area.

Layout and colours follow DESIGN/DASHBOARD_DESIGN.md sections 2 to 5 and 18. The theme is
applied per page: Quasar's palette is replaced (its defaults are blue) and the token
stylesheet is linked, with the Inter font served from this package. The header carries the
Tracko logo, recoloured to the theme by tools/make_logo_assets.py (the brand original is blue
on white, which the design forbids).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from nicegui import ui

from tracko_anpr.dashboard.components.status_panel import status_panel

APP_TITLE = "Vehicle ANPR POC"
APP_SUBTITLE = "Detection • Tracking • Recognition"
ENVIRONMENT_BADGE = "POC – Indian Roads"
LOGO_URL = "/dashboard-static/logo"


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str
    path: str


NAV_ITEMS = (
    NavItem("overview", "Overview", "home", "/"),
    NavItem("upload", "Upload & Process", "upload", "/upload"),
    NavItem("analysis", "Video Analysis", "play_circle", "/analysis"),
    NavItem("history", "Detection History", "history", "/history"),
    NavItem("registry", "Demo Registry", "storage", "/registry"),
    NavItem("analytics", "Analytics", "bar_chart", "/analytics"),
    NavItem("settings", "Settings", "settings", "/settings"),
)


def apply_theme() -> None:
    """Colours and fonts for this page. Every Quasar colour that could be blue is replaced."""
    ui.dark_mode(True)
    ui.colors(
        primary="#36d428",
        secondary="#166522",
        accent="#facc15",
        dark="#141414",
        dark_page="#080808",
        positive="#36d428",
        negative="#ef4444",
        info="#858585",
        warning="#f59e0b",
    )
    ui.add_head_html('<link rel="stylesheet" href="/dashboard-static/theme.css">')


def header() -> None:
    with ui.header(fixed=True, bordered=False).classes("tk-header items-center px-4 py-0 justify-between"):
        with ui.row().classes("items-center gap-4 no-wrap"):
            # The brand: the full logo (car mark + wordmark) on wide screens, the mark alone on narrow ones.
            ui.image(f"{LOGO_URL}/logo-full.png").classes("tk-logo-full").props("no-spinner no-transition")
            ui.image(f"{LOGO_URL}/mark.png").classes("tk-logo-mark").props("no-spinner no-transition")
            with ui.column().classes("gap-0 tk-app-text"):
                ui.label(APP_TITLE).classes("tk-app-title")
                ui.label(APP_SUBTITLE).classes("tk-app-subtitle")
        with ui.row().classes("items-center gap-4 no-wrap"):
            with ui.element("span").classes("tk-badge"):
                ui.element("span").classes("tk-dot")
                ui.label(ENVIRONMENT_BADGE)
            ui.element("span").style("width: 1px; height: 28px; background: var(--border-color)")
            # Decorative in the POC: no notifications and no login (DESIGN section 4).
            ui.icon("notifications_none").classes("text-2xl").style("color: var(--text-secondary)")
            ui.icon("account_circle").classes("text-3xl").style("color: var(--text-muted)")


def sidebar(active: str) -> None:
    with (
        ui.left_drawer(value=True, fixed=True, bordered=False)
        .props("width=210 breakpoint=900")
        .classes("tk-sidebar column no-wrap justify-between")
    ):
        with ui.element("nav").classes("tk-nav"):
            for item in NAV_ITEMS:
                classes = "tk-nav-item active" if item.key == active else "tk-nav-item"
                with ui.link(target=item.path).classes(classes):
                    ui.icon(item.icon)
                    ui.label(item.label)
        status_panel()


@contextmanager
def frame(active: str, title: str | None = None, subtitle: str | None = None) -> Iterator[ui.element]:
    """Theme, header and sidebar around a page; yields the content column."""
    apply_theme()
    header()
    sidebar(active)
    with ui.column().classes("w-full gap-4") as content:
        if title:
            with ui.column().classes("gap-0"):
                ui.label(title).classes("tk-page-title")
                if subtitle:
                    ui.label(subtitle).classes("tk-page-subtitle")
        yield content
