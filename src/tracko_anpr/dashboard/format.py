"""Small formatting helpers shared by the pages."""

from __future__ import annotations

from datetime import datetime

VEHICLE_ICONS = {
    "Car": "directions_car",
    "Motorcycle": "two_wheeler",
    "Bus": "directions_bus",
    "Truck": "local_shipping",
}
STATUS_LABELS = {"confirmed": "Confirmed", "unconfirmed": "Unconfirmed", "not_detected": "Not detected"}


def human_size(size: int | None) -> str:
    if size is None:
        return "—"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit in ("B", "KB") else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} GB"


def human_duration(seconds: float | None) -> str:
    """1:50 or 1:02:03."""
    if seconds is None:
        return "—"
    minutes, secs = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def video_time(seconds: float | None) -> str:
    """hh:mm:ss, as the detections tables show it."""
    if seconds is None:
        return "—"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def minutes_seconds(seconds: float) -> str:
    """3 min 42 sec, as the Avg. Processing Time card shows it."""
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes} min {secs:02d} sec" if minutes else f"{secs} sec"


def when(moment: datetime | None, seconds: bool = False) -> str:
    if moment is None:
        return "—"
    pattern = "%d %b %Y, %H:%M:%S" if seconds else "%d %b %Y, %H:%M"
    return moment.astimezone().strftime(pattern)


def percent(share: float | None) -> str:
    return "—" if share is None else f"{100 * share:.1f}%"


def thousands(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"
