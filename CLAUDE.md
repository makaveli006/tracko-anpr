# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Offline proof of concept for Indian vehicle detection, tracking and number plate recognition (ANPR) on uploaded MP4 videos, shown through a dashboard for a leadership demo. It is not a live-camera system.

**Status: scaffold only.** `src/tracko_anpr/__init__.py` holds a placeholder `main()`. None of the pipeline, API, database or dashboard exists yet, and no dependencies, tests or linter are configured.

The two specs are the source of truth — read them before designing or building anything:

- `ARCHITECTURE.md` — pipeline stages, API endpoints, database tables, storage folders, what is out of scope.
- `DESIGN/DASHBOARD_DESIGN.md` — dashboard pages, layout, colors and states. The reference screenshot is `DESIGN/Dark ANPR Surveillance Dashboard.png`. The theme is black/charcoal with green as the primary accent and amber for plates and warnings; blue, purple and white page backgrounds are forbidden, so NiceGUI/Quasar's default blue theme colors must be overridden.

## Environment

The host is Windows Server 2022, but the entire application runs inside WSL 2 (default distro Ubuntu 24.04): the web app, the worker, the models and the database. Nothing runs natively on Windows. The repo stays on the Windows filesystem at `C:\Users\ontashai\Desktop\tracko-anpr` (`/mnt/c/Users/ontashai/Desktop/tracko-anpr` from WSL). The user decided on 2026-11-06 to keep development there: a move into the WSL home was tried and undone as too confusing, so do not move or copy the repo into WSL. `.venv` is a Linux venv created by uv in WSL, so run all Python, uv and Docker commands through WSL, not Windows PowerShell:

```bash
wsl -e bash -lic "cd /mnt/c/Users/ontashai/Desktop/tracko-anpr && <command>"
```

Use `bash -lic` so the login profile loads (uv is in `~/.local/bin`, Node comes from nvm).

The database is PostgreSQL 18 (stable) in a Docker container inside WSL, using the native Docker engine in Ubuntu (not Docker Desktop). Only PostgreSQL is containerised; the application and the GPU models run directly in WSL. Keep the database data in a named Docker volume, not a bind mount under `/mnt/c`. The `postgres:18` image expects its volume at `/var/lib/postgresql`, not the older `/var/lib/postgresql/data`.

## Commands

```bash
uv sync                 # install the project and dependencies into .venv
uv run tracko-anpr      # run the entry point (tracko_anpr:main)
uv add <package>        # add a dependency (updates pyproject.toml and uv.lock)
```

Python is pinned to 3.12 (`.python-version`); the build backend is `uv_build` with a `src/` layout.

The backend must run on FastAPI 0.162.0 exactly (`uv add "fastapi==0.162.0"` when it is first added). NiceGUI is built on FastAPI and shares that install, so pick a NiceGUI version whose FastAPI requirement allows 0.162.0.

Decisions made by the user (2026-11-06), none of it installed or configured yet:

- **Database layer:** SQLAlchemy with Alembic migrations and the psycopg 3 driver.
- **Versions:** apart from FastAPI (0.162.0) and PostgreSQL (18), take the latest stable release at install time and rely on `uv.lock` to lock it. PyTorch and PaddlePaddle are the exception: their versions are constrained by the GPU driver (see Open dependencies).
- **Web app:** one process, with NiceGUI mounted on the FastAPI app. It must run as a single server process because NiceGUI keeps session state in memory. Splitting the dashboard and API into two services is listed in `ARCHITECTURE.md` as a future implementation; do not build it now, but keep dashboard code calling shared service functions so the split stays possible.
- **Build order:** pipeline first. Get one video through detection, tracking, plate detection and OCR from the command line before any database, API or dashboard work.
- **Plate detector:** test the downloaded weights in `pretrained-numberplate-weight/` on the user's own clips first; fine-tune YOLO26s on the IURS-NPDS dataset (19,309 images) only if they miss plates.
- **Job hand-off:** the `processing_jobs` table in PostgreSQL is the queue. FastAPI inserts a queued row, the worker polls and claims it, writes stage and progress back, and must reset jobs left at "processing" by a crash when it starts.
- **Video input:** the pipeline takes MP4 only, at any frame rate; 30 FPS is only the suggestion. Never hardcode 30: read the frame rate from each video and derive everything time-based from it (timestamps, the tracker's lost-track buffer, chart buckets, the annotated output's frame rate). Clips in another container or resolution are converted to 1080p H.264 MP4 with FFmpeg beforehand, keeping their own frame rate. The source clips are in `videos/` (git-ignored): six MP4s at 29.97 to 60 FPS used as they are, and two 2K `.webm` files whose MP4 versions go to `videos/converted/`. FFmpeg 6.1.1 was installed in WSL with apt on 2026-11-06; system installs like this are logged under "System Setup — Installation Commands" in `ARCHITECTURE.md`, so add new ones there.
- **Vehicle classes:** four only (car, motorcycle, bus, truck). Auto-rickshaw support is a future implementation. The class is called "Motorcycle" everywhere, never "Bike".
- **Licence:** YOLO26 and weights trained from it are AGPL-3.0. Proceed with YOLO26 for the POC; the question is flagged in `ARCHITECTURE.md` to settle before production or customer use.
- **Demo registry:** fictional records are generated from a share of the plates recognized in the demo videos, so both matches and non-matches appear.
- **Dashboard:** the Overview has a video selector, and the five summary cards switch between the selected video and all videos. "Detections Over Time" counts new vehicles per 10-second bucket. Filled green backgrounds use dark green `#166522` with white text, not white on bright green. The header bell and profile icon are decorative: no login, no notifications.
- **Code quality:** Ruff for both linting and formatting, pytest for tests. Once added as dev dependencies the commands are `uv run ruff check`, `uv run ruff format`, `uv run pytest`, and `uv run pytest path/to/test_file.py::test_name` for a single test.

## Planned architecture

One video flows through these stages inside a separate worker process, never inside the web server:

1. NiceGUI upload → FastAPI creates a job
2. OpenCV/FFmpeg decode
3. YOLO26m vehicle detection (cars, motorcycles, buses, trucks; input 1536, FP16)
4. TrackTrack tracking (built into Ultralytics)
5. Vehicle crop from the original frame
6. YOLO26s plate detection (Indian fine-tuned weights, input 640)
7. Awiros-ANPR-OCR text recognition (PaddlePaddle, PP-OCRv5 based)
8. Multi-frame consensus per track
9. PostgreSQL rows + files under `storage/`
10. Annotated H.264 MP4 render
11. FastAPI results → NiceGUI dashboard

Ultralytics has TrackTrack built in — do not look for a fork or write a custom integration. It was added on 2026-06-09 (PR #24371), is in the current release (8.4.203, checked 2026-11-06) and is the default tracker in the official docs (https://docs.ultralytics.com/modes/track/). Use it through the normal tracking call with `tracker="tracktrack.yaml"`; copy that file from `ultralytics/cfg/trackers/` to customise it. Its defaults: camera motion compensation on (`gmc_method: sparseOptFlow`), lost tracks kept 30 frames (`track_buffer`), ReID off (`with_reid: False`). Not yet installed or run in this repo.

Rules from the specs that are easy to break:

- Plate and vehicle crops must come from the original 1920×1080 frame, never from the resized inference frame.
- Track IDs are local to one processing job. Identify a track by job/video id plus track id, and never present it as a permanent vehicle identity.
- A plate is shown as confirmed only after multi-frame validation; otherwise it is pending or unconfirmed.
- "Recognition coverage" is validated plates ÷ eligible tracked vehicles. Do not label it, or confidence averages, as accuracy.
- The demo registry is fictional data and must be labelled as such; there is no real registration lookup.
- Mock dashboard data must be labelled "Demo Data" and kept separate from real API responses. Never show fake progress or fake completed results.
- Video files live on disk under `storage/`; PostgreSQL stores only references.
- Out of scope: RTSP, WebRTC, live cameras, Redis/Celery, cloud services, microservices, React, model training in the dashboard.

## Open dependencies

These are assumed by the specs but not yet confirmed or available:

- No plate detector has been chosen. Untested third-party candidates are in `pretrained-numberplate-weight/` (see its README); none is a confirmed fit, so fine-tuning YOLO26s may still be needed.
- `Awiros/anpr-ocr` on Hugging Face is public, ungated and Apache-2.0; `model.safetensors` (149 MB) downloads without login (checked 2026-11-06). It is not a pip-installable pipeline: its `test.py` builds the network from the PaddleOCR source tree (`ppocr`, cloned from GitHub) and loads the safetensors into it, so the project needs a pinned PaddleOCR checkout plus `paddlepaddle-gpu>=2.6.0`. Input is a plate crop resized to 48 px high (max 320 wide); output is uppercase text plus a CTC confidence. Accuracy figures are the publisher's own; not yet run here.
- PyTorch and PaddlePaddle clash in one environment (resolution tested with `uv pip compile` on 2026-11-06, nothing installed):
  - The NVIDIA driver is 572.16, which reports CUDA 12.8. PyPI's default `torch` (2.15.0) is built against CUDA 13 libraries and probably needs a newer driver; the newest CUDA 12.6 build is `torch==2.14.1+cu126` from `https://download.pytorch.org/whl/cu126`.
  - GPU builds of PaddlePaddle 3.x come from Paddle's own index (`https://www.paddlepaddle.org.cn/packages/stable/cu126/`, latest 3.3.1), not PyPI. PyPI only has the old 2.6.2, which uv silently falls back to.
  - `torch==2.14.1+cu126` pins `nvidia-cudnn-cu12==9.10.2.21` and `paddlepaddle-gpu==3.3.1` pins `==9.5.1.17`, so uv cannot resolve them together.
  - **Decision (user, 2026-11-06): keep the current driver, no upgrade.** The main environment uses `torch==2.14.1+cu126` (not the PyPI default). The OCR runs in its own uv project with its own `.venv` (`paddlepaddle-gpu==3.3.1`, CUDA 12.6 build, plus a pinned PaddleOCR source checkout) and as a separate process that the worker sends plate crops to. That project is `ocr/` at the repo root (package `anpr_ocr`, created with `uv init --no-workspace` so it is not a workspace member and has its own lock file); the PaddleOCR source goes in `ocr/vendor/`. Run its commands from inside `ocr/`. Never add PaddlePaddle to the main `pyproject.toml`, and never make `ocr/` a uv workspace member.

## Repository notes

- The folder skeleton exists but holds no logic yet (created 2026-11-06). Main package `src/tracko_anpr/` has empty subpackages `api`, `dashboard` (`components`, `pages`), `db`, `worker` and `pipeline`. `models/` holds the weights the app loads and `storage/` holds uploads and generated files; both are git-ignored apart from `.gitkeep`. `migrations/`, `alembic.ini` and `docker-compose.yml` are not created yet.

- `initial-images/` is git-ignored reference material.
- The folder is `DESIGN/` (uppercase); mind the case when working from WSL.
