"""Is the system ready? The sidebar's status panel must show the truth, never a false green.

Checked: the database (reachable and migrated), a worker (one has reported within the last
few seconds, idle or on a job), the GPU (nvidia-smi), the model files, the plate reader's
installation and FFmpeg. `ready` is true only when the database, a worker and the models
are all there, because without them an upload could not be processed.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tracko_anpr.config import Settings
from tracko_anpr.db.models import PROCESSING, AppSetting, ProcessingJob
from tracko_anpr.db.session import current_revision

WORKER_HEARTBEAT_KEY = "worker_heartbeat"
WORKER_ALIVE_SECONDS = 15
"""An idle worker writes its heartbeat every poll (2 s)."""
BUSY_WORKER_ALIVE_SECONDS = 60
"""On a job the heartbeat comes with progress reports, which can pause for the reader's start-up or a plate batch."""


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    short: str = ""
    """A few words for the sidebar panel, where `detail` would wrap; empty means use `detail`."""


@dataclass(frozen=True)
class SystemStatus:
    ready: bool
    checks: list[Check]
    gpu: str
    models: str
    ocr: str
    checked_at: datetime


def record_worker_heartbeat(session: Session, worker_id: str) -> None:
    """Called by an idle worker on every poll, so the dashboard knows one is running."""
    row = session.get(AppSetting, WORKER_HEARTBEAT_KEY)
    value = {"worker_id": worker_id, "at": datetime.now(UTC).isoformat()}
    if row is None:
        session.add(AppSetting(key=WORKER_HEARTBEAT_KEY, value=value))
    else:
        row.value = value
    session.flush()


def worker_check(session: Session, now: datetime | None = None) -> Check:
    now = now or datetime.now(UTC)
    latest: datetime | None = None
    who = ""
    row = session.get(AppSetting, WORKER_HEARTBEAT_KEY)
    if row is not None and isinstance(row.value, dict) and row.value.get("at"):
        latest = datetime.fromisoformat(row.value["at"])
        who = str(row.value.get("worker_id", ""))
    running = session.scalar(
        select(ProcessingJob).where(ProcessingJob.status == PROCESSING).order_by(ProcessingJob.heartbeat_at.desc())
    )
    allowed = WORKER_ALIVE_SECONDS
    busy = ""
    if running is not None and running.heartbeat_at is not None:
        beat = running.heartbeat_at if running.heartbeat_at.tzinfo else running.heartbeat_at.replace(tzinfo=UTC)
        if latest is None or beat > latest:
            latest, who = beat, running.worker_id or who
            # On a job the heartbeat comes with progress, and some stretches report none for a while
            # (the reader's 20-second start-up, a batch of plates): allow the job's own stall limit.
            allowed = BUSY_WORKER_ALIVE_SECONDS
            busy = f", processing job {running.id}"
    if latest is None:
        return Check("worker", False, "No worker has ever reported. Start one: uv run tracko-anpr worker")
    age = (now - latest).total_seconds()
    if age > allowed:
        return Check("worker", False, f"Worker {who} last reported {age:.0f} s ago; it has probably stopped.")
    return Check("worker", True, f"Worker {who} reported {age:.0f} s ago{busy}.")


def database_check(engine: Engine) -> Check:
    try:
        revision = current_revision(engine)
    except Exception as error:  # the message is for the status panel; any failure is "not reachable"
        return Check(
            "database", False, f"Not reachable: {type(error).__name__}. Is the container up (docker compose up -d)?"
        )
    if revision is None:
        return Check("database", False, "Reachable but not migrated. Run: uv run alembic upgrade head")
    return Check("database", True, f"PostgreSQL reachable, migration {revision}.")


def gpu_check() -> Check:
    tool = shutil.which("nvidia-smi")
    if tool is None:
        return Check("gpu", False, "nvidia-smi not found; no NVIDIA GPU visible.")
    try:
        output = subprocess.run(
            [tool, "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip().splitlines()  # fmt: skip
    except (subprocess.SubprocessError, OSError) as error:
        return Check("gpu", False, f"nvidia-smi failed: {error}")
    if not output:
        return Check("gpu", False, "nvidia-smi reports no GPU.")
    name, total, used = (part.strip() for part in output[0].split(",")[:3])
    gigabytes = round(int(total) / 1024)
    vendor = "NVIDIA" if "nvidia" in name.lower() else name
    return Check("gpu", True, f"{name} ({gigabytes} GB, {used} MiB in use)", short=f"{vendor} ({gigabytes} GB)")


def models_check(settings: Settings) -> Check:
    missing = [
        path.name
        for path in (settings.vehicle_weights, settings.plate_weights, settings.ocr_model)
        if not path.is_file()
    ]
    if missing:
        return Check(
            "models", False, f"Missing model files: {', '.join(missing)} (see 'Model Files' in ARCHITECTURE.md)."
        )
    return Check("models", True, f"{settings.vehicle_weights.stem} / {settings.plate_weights.stem}")


def ocr_check(settings: Settings) -> Check:
    executable = settings.ocr_project / ".venv" / "bin" / "anpr-ocr"
    if not executable.is_file():
        return Check("ocr", False, f"Plate reader not installed at {executable}; run `uv sync` inside ocr/.")
    return Check("ocr", True, "Awiros-ANPR-OCR installed (started by the worker).")


def ffmpeg_check() -> Check:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        return Check("ffmpeg", False, f"Not on PATH: {', '.join(missing)}.")
    return Check("ffmpeg", True, "FFmpeg and ffprobe found.")


def system_status(settings: Settings, engine: Engine, session: Session | None) -> SystemStatus:
    """All checks at once. `session` may be None when the database itself is down."""
    checks = [database_check(engine)]
    if session is not None and checks[0].ok:
        checks.append(worker_check(session))
    else:
        checks.append(Check("worker", False, "Cannot tell without the database."))
    checks += [gpu_check(), models_check(settings), ocr_check(settings), ffmpeg_check()]
    by_name = {check.name: check for check in checks}
    ready = all(by_name[name].ok for name in ("database", "worker", "models", "ocr", "ffmpeg"))
    return SystemStatus(
        ready=ready,
        checks=checks,
        gpu=(by_name["gpu"].short or by_name["gpu"].detail) if by_name["gpu"].ok else "no GPU",
        models=by_name["models"].detail if by_name["models"].ok else "missing",
        ocr="Awiros-ANPR-OCR" if by_name["ocr"].ok else "not installed",
        checked_at=datetime.now(UTC),
    )
