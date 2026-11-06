"""Project settings: where files live and the defaults the pipeline runs with.

Values come from environment variables, with a `.env` file in the project root
read first if it exists. `.env` is git-ignored; `.env.example` shows what it may hold.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote


def find_project_root(start: Path | None = None) -> Path:
    """Folder that holds `pyproject.toml`, found by walking up from `start` (default: this file)."""
    override = os.environ.get("TRACKO_ANPR_ROOT")
    if override:
        return Path(override).resolve()
    here = (start or Path(__file__)).resolve()
    for folder in (here, *here.parents):
        if (folder / "pyproject.toml").is_file() and (folder / "src" / "tracko_anpr").is_dir():
            return folder
    return Path.cwd()


def read_env_file(path: Path) -> dict[str, str]:
    """Parse `KEY=value` lines. Blank lines and lines starting with `#` are skipped."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


@dataclass(frozen=True)
class Settings:
    """Everything configurable, resolved once. Paths are absolute."""

    root: Path

    # Vehicle detection and tracking (ARCHITECTURE.md sections 5 and 6)
    vehicle_weights: Path
    vehicle_image_size: int
    vehicle_confidence: float
    tracker_lost_seconds: float

    # Number plate reading (ARCHITECTURE.md section 9); runs in the separate `ocr/` environment
    ocr_project: Path
    ocr_model: Path
    ocr_dictionary: Path

    # Database (ARCHITECTURE.md section 11)
    database_url: str

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def storage_dir(self) -> Path:
        return self.root / "storage"

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def processed_dir(self) -> Path:
        return self.storage_dir / "processed"

    @property
    def vehicle_crops_dir(self) -> Path:
        return self.storage_dir / "vehicle_crops"

    @property
    def plate_crops_dir(self) -> Path:
        return self.storage_dir / "plate_crops"


def build_database_url(env: dict[str, str]) -> str:
    """Connection URL for SQLAlchemy with the psycopg 3 driver."""
    explicit = env.get("TRACKO_DATABASE_URL")
    if explicit:
        return explicit
    user = quote(env.get("POSTGRES_USER", "tracko"), safe="")
    password = quote(env.get("POSTGRES_PASSWORD", ""), safe="")
    host = env.get("POSTGRES_HOST", "127.0.0.1")
    port = env.get("POSTGRES_PORT", "5432")
    database = env.get("POSTGRES_DB", "tracko_anpr")
    credentials = f"{user}:{password}" if password else user
    return f"postgresql+psycopg://{credentials}@{host}:{port}/{database}"


def load_settings(root: Path | None = None, environ: dict[str, str] | None = None) -> Settings:
    """Build settings from `.env` and the environment; real environment variables win."""
    root = (root or find_project_root()).resolve()
    env = read_env_file(root / ".env")
    env.update(os.environ if environ is None else environ)

    models = root / "models"
    return Settings(
        root=root,
        vehicle_weights=Path(env.get("TRACKO_VEHICLE_WEIGHTS", models / "yolo26m.pt")),
        vehicle_image_size=int(env.get("TRACKO_VEHICLE_IMAGE_SIZE", "1536")),
        vehicle_confidence=float(env.get("TRACKO_VEHICLE_CONFIDENCE", "0.1")),
        tracker_lost_seconds=float(env.get("TRACKO_TRACKER_LOST_SECONDS", "1.0")),
        ocr_project=root / "ocr",
        ocr_model=Path(env.get("TRACKO_OCR_MODEL", models / "awiros" / "model.safetensors")),
        ocr_dictionary=Path(env.get("TRACKO_OCR_DICTIONARY", models / "awiros" / "en_dict.txt")),
        database_url=build_database_url(env),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The settings for this process, loaded on first use."""
    return load_settings()
