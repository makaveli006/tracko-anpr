"""Demo Registry (DESIGN section 15): FICTIONAL vehicle records, and the recognised numbers matched against them.

"Demonstration Data Only" is displayed at the top of the page and in every lookup answer.
Nothing here is, or implies, real registration information.

Lists and descriptions (Axis item 5): a record can belong to a named list ("Staff", "Visitors",
"Watch") and carry an operator's description; a recognised number can be added to a list from
this page, and records can be imported from a CSV. Everything added is fictional and says so.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from nicegui import events, ui

from tracko_anpr.dashboard.components.registry_dialog import show_registry_dialog
from tracko_anpr.dashboard.format import VEHICLE_ICONS
from tracko_anpr.dashboard.layout import frame
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.services import registry
from tracko_anpr.services.registry import DISCLAIMER, RecognizedNumber, RegistryError, RegistryRecord


def _load(session, search: str | None, list_name: str | None):
    return (
        registry.list_entries(session, search, list_name=list_name),
        registry.recognized_numbers(session, search),
        registry.count(session),
        registry.lookup(session, search) if search else None,
        registry.lists(session),
    )


def _url(search: str | None, list_name: str | None = None) -> str:
    values = {"q": search, "list": list_name}
    tail = urlencode({k: v for k, v in values.items() if v})
    return "/registry" + (f"?{tail}" if tail else "")


class RegistryPage:
    def __init__(self, search: str | None, list_name: str | None) -> None:
        self.search, self.list_name = search, list_name

    async def reload(self) -> None:
        ui.navigate.to(_url(self.search, self.list_name))

    async def add(self, number: str, vehicle_type: str | None = None) -> None:
        await show_registry_dialog(number=number, vehicle_type=vehicle_type, on_change=self.reload)

    async def edit(self, record: RegistryRecord) -> None:
        await show_registry_dialog(record=record, on_change=self.reload)

    async def on_import(self, event: events.UploadEventArguments) -> None:
        text = await event.file.text()
        try:
            outcome = await query(registry.import_csv, text, event.file.name)
        except RegistryError as error:
            ui.notify(str(error), type="negative", close_button=True, timeout=0)
            return
        message = f"Imported {outcome.created} new and updated {outcome.updated} fictional records."
        if outcome.skipped:
            first = "; ".join(f"line {line}: {reason}" for line, reason in outcome.skipped[:3])
            message += f" Skipped {len(outcome.skipped)}: {first}"
        ui.notify(message, type="positive" if not outcome.skipped else "warning", close_button=True, timeout=0)
        await self.reload()

    def copy_link(self) -> None:
        ui.run_javascript(
            f"navigator.clipboard.writeText(window.location.origin + {json.dumps(_url(self.search, self.list_name))})"
        )
        ui.notify("Link to this search copied.", type="positive")

    # --- tables ------------------------------------------------------------------------------------

    def records_table(self, entries: list[RegistryRecord]) -> None:
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
                    "List",
                    "Description",
                    "",
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
                        with ui.element("td"):
                            ui.label(r.list_name or "—").classes("tk-green font-medium" if r.list_name else "tk-muted")
                        with ui.element("td"):
                            ui.label(r.description or "—").classes("" if r.description else "tk-muted")
                        with ui.element("td"):
                            ui.button("Edit", color=None, on_click=lambda _, rec=r: self.edit(rec)).props(
                                "flat dense no-caps"
                            ).classes("tk-link text-xs")

    def matches_table(self, numbers: list[RecognizedNumber]) -> None:
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
                    "",
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
                            self.registry_state(n)
                        with ui.element("td"):
                            self.record_text(n)
                        with ui.element("td"):
                            if n.exact:
                                ui.button("Edit", color=None, on_click=lambda _, rec=n.record: self.edit(rec)).props(
                                    "flat dense no-caps"
                                ).classes("tk-link text-xs")
                            else:
                                ui.button(
                                    "Add to list",
                                    color=None,
                                    on_click=lambda _, num=n.registration_number, t=n.vehicle_type: self.add(num, t),
                                ).props("flat dense no-caps").classes("tk-link text-xs")

    @staticmethod
    def registry_state(n: RecognizedNumber) -> None:
        if n.exact:
            with ui.row().classes("items-center gap-1 no-wrap tk-green"):
                ui.icon("check_circle").classes("text-base")
                ui.label("Match" + (f" · {n.record.list_name}" if n.record.list_name else "")).classes("font-medium")
        elif n.possible:
            with ui.row().classes("items-center gap-1 no-wrap tk-amber"):
                ui.icon("help_outline").classes("text-base")
                ui.label("Possible match").classes("font-medium")
                ui.tooltip(f"One character away ({n.match.difference}); not asserted.")
        else:
            with ui.row().classes("items-center gap-1 no-wrap tk-secondary"):
                ui.icon("remove_circle_outline").classes("text-base")
                ui.label("No match")

    @staticmethod
    def record_text(n: RecognizedNumber) -> None:
        r = n.record
        if r is None:
            ui.label("—").classes("tk-muted")
            return
        text = f"{r.owner_name} · {r.vehicle_description} · {r.colour} · {r.registered_at}"
        if n.possible:
            text = f"{r.registration_number} · {text} ({n.match.difference})"
        elif r.description:
            text += f" · {r.description}"
        ui.label(text).classes("tk-amber" if n.possible else "")

    # --- the page --------------------------------------------------------------------------------

    def build(self, entries, numbers, total, found, lists) -> None:
        search, list_name = self.search, self.list_name
        with ui.element("div").classes("tk-banner amber w-full"):
            ui.icon("warning")
            with ui.column().classes("gap-0"):
                ui.label("Demonstration Data Only").classes("font-semibold")
                ui.label(DISCLAIMER).classes("text-sm font-normal")
        with ui.element("div").classes("tk-card w-full"):
            with ui.row().classes("w-full items-end gap-3 no-wrap"):
                box = (
                    ui.input(
                        "Search a registration number", value=search or "", placeholder="e.g. KL07 or a full number"
                    )
                    .props("outlined dense dark clearable")
                    .style("min-width: 300px")
                )
                box.on("keydown.enter", lambda: ui.navigate.to(_url(box.value, list_name)))
                ui.button(
                    "Search", color=None, icon="search", on_click=lambda: ui.navigate.to(_url(box.value, list_name))
                ).classes("tk-secondary")
                options = {None: "All lists", **{name: f"{name} ({count})" for name, count in lists}}
                ui.select(
                    options,
                    value=list_name if list_name in options else None,
                    label="List",
                    on_change=lambda e: ui.navigate.to(_url(search, e.value)),
                ).props("outlined dense dark options-dense").style("min-width: 170px")
                if search or list_name:
                    ui.button("Clear", color=None, on_click=lambda: ui.navigate.to("/registry")).classes(
                        "tk-link"
                    ).props("flat")
                    ui.button("Copy link", color=None, icon="link", on_click=self.copy_link).classes("tk-secondary")
                ui.element("div").style("flex: 1 1 0")
                ui.upload(
                    label="Import CSV",
                    auto_upload=True,
                    max_files=1,
                    on_upload=self.on_import,
                    on_rejected=lambda: ui.notify("That file was not accepted: it must be a .csv.", type="warning"),
                ).props('accept=".csv,text/csv" flat dense').classes("tk-upload-inline")
                ui.button(
                    "Template",
                    color=None,
                    icon="description",
                    on_click=lambda: ui.navigate.to("/api/registry/import-template.csv", new_tab=True),
                ).classes("tk-link").props("flat")
                ui.label(f"{total} fictional records").classes("tk-secondary text-sm")
            if search:
                shown = search.upper().replace(" ", "")
                with ui.row().classes("w-full items-center gap-3 no-wrap mt-3"):
                    if found is not None and found.exact:
                        r = found.record
                        tone, icon = "green", "check_circle"
                        answer = f"{shown}: Match — {r.owner_name}, {r.vehicle_description}, {r.colour}"
                        answer += f", list {r.list_name}" if r.list_name else ""
                        answer += " (fictional)"
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
                    with ui.element("div").classes(f"tk-banner {tone}").style("flex: 1 1 0"):
                        ui.icon(icon)
                        ui.label(answer)
                    if found is None or not found.exact:
                        ui.button(
                            "Add to a list", color=None, icon="playlist_add", on_click=lambda: self.add(shown)
                        ).classes("tk-secondary")
        with ui.element("div").classes("tk-card w-full"):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label("Recognised Numbers vs Registry").classes("tk-card-title")
                exact = sum(1 for n in numbers if n.exact)
                possible = sum(1 for n in numbers if n.possible)
                ui.label(f"{exact} match · {possible} possible · {len(numbers) - exact - possible} no match").classes(
                    "tk-secondary text-sm"
                )
            if numbers:
                self.matches_table(numbers)
                ui.label(
                    "Every number the pipeline confirmed in the processed videos, looked up in the fictional "
                    "registry. A match means a fictional record was generated for it, nothing more; a possible "
                    "match is a record one character away, shown so a misread can be noticed, never asserted. "
                    '"Add to list" creates a fictional record for the number in a named list.'
                ).classes("tk-muted text-xs mt-1")
            else:
                ui.label(
                    "No confirmed numbers yet." if not search else "No confirmed number matches the search."
                ).classes("tk-muted mt-2")
        with ui.element("div").classes("tk-card w-full"):
            ui.label("Registry Records" + (f" · list {list_name}" if list_name else "")).classes("tk-card-title")
            if entries:
                self.records_table(entries)
                ui.label(
                    "Generated with `tracko-anpr seed-registry` (fictional records for about half of the "
                    "recognised numbers, near-miss records one character from some of the others, plus a few "
                    "numbers that appear in no video), added from this page, or imported from a CSV."
                ).classes("tk-muted text-xs mt-1")
            elif list_name or search:
                ui.label("No records match.").classes("tk-muted mt-2")
            else:
                ui.label("The registry is empty. Generate it with: uv run tracko-anpr seed-registry").classes(
                    "tk-muted mt-2"
                )


@ui.page("/registry")
async def registry_page(q: str = "", list: str = "") -> None:  # noqa: A002 - the URL parameter is called `list`
    search = q.strip() or None
    list_name = list.strip() or None
    page = RegistryPage(search, list_name)
    loaded = await query(_load, search, list_name)
    with frame("registry", "Demo Registry", "Fictional vehicle registrations for the demonstration"):
        page.build(*loaded)
