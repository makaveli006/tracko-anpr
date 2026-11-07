"""Files the application serves: videos, annotated videos, result files and crop images.

The database stores paths relative to the project root. Anything served to a browser must
lie under `storage/` (or be a registered video's own file), so a request can never reach
other files on the machine.
"""

from __future__ import annotations

from pathlib import Path

from tracko_anpr.config import Settings


class FileNotAvailable(FileNotFoundError):
    """The file is not there (yet), or lies outside what may be served."""


def resolve(settings: Settings, stored_path: str | None) -> Path:
    """The absolute path for a stored (root-relative or absolute) path. Does not check it exists."""
    if not stored_path:
        raise FileNotAvailable("No file recorded.")
    path = Path(stored_path)
    return path if path.is_absolute() else settings.root / path


def storage_file(settings: Settings, stored_path: str | None) -> Path:
    """A file under `storage/` that exists; anything else is refused."""
    path = resolve(settings, stored_path).resolve()
    storage = settings.storage_dir.resolve()
    if storage not in path.parents:
        raise FileNotAvailable(f"Not a file under storage/: {stored_path}")
    if not path.is_file():
        raise FileNotAvailable(f"File not found: {stored_path}")
    return path


def image_file(settings: Settings, relative_path: str) -> Path:
    """A crop image under storage/vehicle_crops or storage/plate_crops, by its stored relative path."""
    path = storage_file(settings, relative_path)
    allowed = (settings.vehicle_crops_dir.resolve(), settings.plate_crops_dir.resolve())
    if not any(folder in path.parents for folder in allowed):
        raise FileNotAvailable(f"Not a crop image: {relative_path}")
    if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        raise FileNotAvailable(f"Not an image: {relative_path}")
    return path


def video_file(settings: Settings, stored_path: str | None) -> Path:
    """A registered video's file. Uploads live under storage/; ingested files may be anywhere the user named."""
    path = resolve(settings, stored_path)
    if not path.is_file():
        raise FileNotAvailable(f"Video file not found: {stored_path}")
    return path
