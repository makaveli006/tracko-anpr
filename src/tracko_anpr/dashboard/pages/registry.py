"""Demo Registry (DESIGN section 15): FICTIONAL vehicle records, and the recognised numbers matched against them.

"Demonstration Data Only" is displayed at the top of the page and in every lookup answer.
Nothing here is, or implies, real registration information.
"""

from __future__ import annotations

from urllib.parse import urlencode

from nicegui import ui

from tracko_anpr.dashboard.format import VEHICLE_ICONS
from tracko_anpr.dashboard.layout import frame
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.services import registry
from tracko_anpr.services.registry import DISCLAIMER, RecognizedNumber, RegistryRecord


def _load(session, search: str | None):
    return (
        registry.list_entries(session, search),
        registry.recognized_numbers(session, search),
        registry.count(session),
        registry.lookup(session, search) if search else None,
    )


def _url(search: str | None) -> str:
    return "/registry" + (f"?{urlencode({'q': search})}" if search else "")


def records_table(entries: list[RegistryRecord]) -> None:
    with ui.element("div").classes("tk-table-wrap w-full mt-2"), ui.element("table").classes("tk-html-table"):
        with ui.element("thead"), ui.element("tr"):
            for heading in (
                "Registration",
                "Owner (fictional)",
                "Vehicle",
                "Type",
                "Colour",
                "Registered at",
                "Valid until",
            ):
                with ui.element("th"):
                    ui.label(heading)
        with ui.element("tbody"):
            for r in entries:
                with ui.element("tr"):
                    for value in (
                        r.registration_number,
                        r.owner_name,
                        r.vehicle_description,
                        r.vehicle_type,
                        r.colour,
                        r.registered_at,
                        r.valid_until.strftime("%d %b %Y"),
                    ):
                        with ui.element("td"):
                            ui.label(value).classes("tk-mono" if value == r.registration_number else "")


def matches_table(numbers: list[RecognizedNumber]) -> None:
    with ui.element("div").classes("tk-table-wrap w-full mt-2"), ui.element("table").classes("tk-html-table"):
        with ui.element("thead"), ui.element("tr"):
            for heading in (
                "Recognised number",
                "Vehicle",
                "Seen in",
                "Sightings",
                "Best confidence",
                "Registry",
                "Fictional record",
            ):
                with ui.element("th"):
                    ui.label(heading)
        with ui.element("tbody"):
            for n in numbers:
                with ui.element("tr"):
                    with ui.element("td"):
                        ui.label(n.registration_number).classes("font-semibold tk-mono")
                    with ui.element("td"), ui.row().classes("items-center gap-2 no-wrap"):
                        ui.icon(VEHICLE_ICONS.get(n.vehicle_type, "directions_car")).classes("text-lg tk-secondary")
                        ui.label(n.vehicle_type)
                    with ui.element("td"):
                        ui.label(", ".join(n.videos))
                    with ui.element("td"):
                        ui.label(str(n.sightings)).classes("tk-mono")
                    with ui.element("td"):
                        ui.label(f"{n.best_confidence:.2f}").classes("tk-mono")
                    with ui.element("td"):
                        if n.exact:
                            with ui.row().classes("items-center gap-1 no-wrap tk-green"):
                                ui.icon("check_circle").classes("text-base")
                                ui.label("Match").classes("font-medium")
                        elif n.possible:
                            with ui.row().classes("items-center gap-1 no-wrap tk-amber"):
                                ui.icon("help_outline").classes("text-base")
                                ui.label("Possible match").classes("font-medium")
                                ui.tooltip(f"One character away ({n.match.difference}); not asserted.")
                        else:
                            with ui.row().classes("items-center gap-1 no-wrap tk-secondary"):
                                ui.icon("remove_circle_outline").classes("text-base")
                                ui.label("No match")
                    with ui.element("td"):
                        r = n.record
                        if r is None:
                            ui.label("—").classes("tk-muted")
                        else:
                            text = f"{r.owner_name} · {r.vehicle_description} · {r.colour} · {r.registered_at}"
                            if n.possible:
                                text = f"{r.registration_number} · {text} ({n.match.difference})"
                            ui.label(text).classes("tk-amber" if n.possible else "")


@ui.page("/registry")
async def registry_page(q: str = "") -> None:
    search = q.strip() or None
    entries, numbers, total, found = await query(_load, search)
    with frame("registry", "Demo Registry", "Fictional vehicle registrations for the demonstration"):
        with ui.element("div").classes("tk-banner amber w-full"):
            ui.icon("warning")
            with ui.column().classes("gap-0"):
                ui.label("Demonstration Data Only").classes("font-semibold")
                ui.label(DISCLAIMER).classes("text-sm font-normal")
        with ui.element("div").classes("tk-card w-full"):
            with ui.row().classes("w-full items-end gap-3 no-wrap"):
                box = (
                    ui.input("Search a registration number", value=q, placeholder="e.g. KL07 or a full number")
                    .props("outlined dense dark clearable")
                    .style("min-width: 320px")
                )
                box.on("keydown.enter", lambda: ui.navigate.to(_url(box.value)))
                ui.button(
                    "Search", color=None, icon="search", on_click=lambda: ui.navigate.to(_url(box.value))
                ).classes("tk-secondary")
                if search:
                    ui.button("Clear", color=None, on_click=lambda: ui.navigate.to("/registry")).classes(
                        "tk-link"
                    ).props("flat")
                ui.element("div").style("flex: 1 1 0")
                ui.label(f"{total} fictional records").classes("tk-secondary text-sm")
            if search:
                shown = search.upper().replace(" ", "")
                if found is not None and found.exact:
                    r = found.record
                    tone, icon = "green", "check_circle"
                    answer = f"{shown}: Match — {r.owner_name}, {r.vehicle_description}, {r.colour} (fictional)"
                elif found is not None:
                    r = found.record
                    tone, icon = "amber", "help_outline"
                    answer = (
                        f"{shown}: no exact match; {r.registration_number} is one character away "
                        f"({found.difference}) — {r.owner_name}, {r.vehicle_description}, {r.colour} (fictional, "
                        "not asserted)"
                    )
                else:
                    tone, icon = "gray", "search_off"
                    answer = f"{shown}: no match in the demonstration registry, exact or one character away"
                with ui.element("div").classes(f"tk-banner {tone} mt-3"):
                    ui.icon(icon)
                    ui.label(answer)
        with ui.element("div").classes("tk-card w-full"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label("Recognised Numbers vs Registry").classes("tk-card-title")
                exact = sum(1 for n in numbers if n.exact)
                possible = sum(1 for n in numbers if n.possible)
                ui.label(f"{exact} match · {possible} possible · {len(numbers) - exact - possible} no match").classes(
                    "tk-secondary text-sm"
                )
            if numbers:
                matches_table(numbers)
                ui.label(
                    "Every number the pipeline confirmed in the processed videos, looked up in the fictional "
                    "registry. A match means a fictional record was generated for it, nothing more; a possible "
                    "match is a record one character away, shown so a misread can be noticed, never asserted."
                ).classes("tk-muted text-xs mt-1")
            else:
                ui.label(
                    "No confirmed numbers yet." if not search else "No confirmed number matches the search."
                ).classes("tk-muted mt-2")
        with ui.element("div").classes("tk-card w-full"):
            ui.label("Registry Records").classes("tk-card-title")
            if entries:
                records_table(entries)
                ui.label(
                    "Generated with `tracko-anpr seed-registry`: fictional records for about half of the "
                    "recognised numbers, near-miss records one character from some of the others, plus a few "
                    "numbers that appear in no video."
                ).classes("tk-muted text-xs mt-1")
            else:
                ui.label("The registry is empty. Generate it with: uv run tracko-anpr seed-registry").classes(
                    "tk-muted mt-2"
                )
