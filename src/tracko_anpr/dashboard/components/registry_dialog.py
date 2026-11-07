"""Add a plate to a fictional list, or edit a record's list and description (Axis item 5).

The dialog is anchored to the page's content, as the corrections dialog is, so redrawing the
table behind it does not delete it. The operator's name is the one the corrections remember in
the browser. Everything written here is demonstration data and the dialog says so.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from nicegui import ui

from tracko_anpr.dashboard.components.detection_dialog import OPERATOR_KEY
from tracko_anpr.dashboard.runtime import query
from tracko_anpr.services import registry
from tracko_anpr.services.registry import DISCLAIMER, VEHICLE_TYPES, RegistryError, RegistryRecord

NEW_LIST = "New list…"


async def show_registry_dialog(
    number: str | None = None,
    record: RegistryRecord | None = None,
    vehicle_type: str | None = None,
    on_change: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Open the dialog: with `record`, edit its list and description; otherwise add `number` to a list."""
    names = [name for name, _ in await query(registry.lists)]
    try:
        operator = str(await ui.run_javascript(f"localStorage.getItem({json.dumps(OPERATOR_KEY)}) || ''") or "")
    except Exception:  # a slow or closed client: start with an empty name
        operator = ""
    current = record.list_name if record is not None else None
    shown = record.registration_number if record is not None else (number or "")

    with ui.context.client.content:
        dialog = ui.dialog()
        with dialog, ui.card().classes("tk-card").style("min-width: 520px; max-width: 95vw"):
            ui.label(f"Edit {shown}" if record is not None else f"Add {shown} to a list").classes("tk-card-title")
            ui.label("Fictional demonstration data: the record is invented and is labelled so.").classes(
                "tk-muted text-xs"
            )
            options = [*names, NEW_LIST]
            start = current if current in names else (names[0] if names else NEW_LIST)
            list_select = (
                ui.select(options, value=start, label="List")
                .props("outlined dense dark options-dense")
                .classes("w-full")
            )
            new_name = (
                ui.input("New list name", placeholder="e.g. Staff, Visitors, Watch")
                .props("outlined dense dark")
                .classes("w-full")
            )
            new_name.bind_visibility_from(list_select, "value", value=NEW_LIST)
            description = (
                ui.input("Description (optional)", value=(record.description if record is not None else "") or "")
                .props("outlined dense dark")
                .classes("w-full")
            )
            type_select = None
            if record is None:
                type_select = (
                    ui.select(
                        list(VEHICLE_TYPES),
                        value=vehicle_type if vehicle_type in VEHICLE_TYPES else "Car",
                        label="Vehicle type",
                    )
                    .props("outlined dense dark options-dense")
                    .classes("w-full")
                )
            name_box = ui.input("Your name (optional)", value=operator).props("outlined dense dark").classes("w-full")

            async def save() -> None:
                chosen = (new_name.value or "").strip() if list_select.value == NEW_LIST else list_select.value
                if not chosen:
                    ui.notify("Give the list a name.", type="warning")
                    return
                who = (name_box.value or "").strip()
                try:
                    if record is None:
                        await query(
                            registry.add_to_list, number, chosen, description.value or "", type_select.value, who
                        )
                    else:
                        await query(registry.update_record, record.id, description.value or "", chosen)
                except RegistryError as error:
                    ui.notify(str(error), type="negative", close_button=True)
                    return
                ui.run_javascript(f"localStorage.setItem({json.dumps(OPERATOR_KEY)}, {json.dumps(who)})")
                ui.notify(f"{shown} is in the list {chosen} (fictional record).", type="positive")
                dialog.close()
                if on_change is not None:
                    await on_change()

            async def remove() -> None:
                await query(registry.remove_from_list, record.id)
                ui.notify(f"{shown} removed from its list.", type="info")
                dialog.close()
                if on_change is not None:
                    await on_change()

            with ui.row().classes("gap-2 mt-2"):
                ui.button("Save", color=None, icon="save", on_click=save).classes("tk-primary")
                if record is not None and record.list_name:
                    ui.button("Remove from list", color=None, on_click=remove).classes("tk-secondary")
                ui.button("Cancel", color=None, on_click=dialog.close).classes("tk-link").props("flat")
            ui.label(DISCLAIMER).classes("tk-muted text-xs mt-2")
    dialog.open()
