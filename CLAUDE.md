# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Offline proof of concept for Indian vehicle detection, tracking and number plate recognition (ANPR) on uploaded MP4 videos, shown through a dashboard for a leadership demo. It is not a live-camera system.

**Status: all 14 phases are done (2026-11-07).** Both Python environments are installed and see the GPU, the model files are in `models/`, and one command runs a video through the whole pipeline from the command line (`tracko-anpr process`): vehicle detection and tracking, plate detection, plate reading through the reader service, validation across frames, and the annotated video. Results are files under `storage/` and rows in PostgreSQL (the container, the seven tables, the Alembic migrations and the metric queries exist since Phase 8). The worker (`tracko-anpr worker`, Phase 9) takes queued jobs from the `processing_jobs` table, runs the pipeline and writes progress and results back; `enqueue`, `ingest` and `jobs` feed and watch it. The web app (`tracko-anpr web`, Phase 10) serves the REST API and, mounted on it, NiceGUI, in one process; the service layer in `services/` is shared by both. All seven dashboard pages exist (Phases 11 to 13): Overview, Upload & Process, Video Analysis, Detection History, Demo Registry, Analytics and Settings, plus `tracko-anpr seed-registry` for the fictional registry. Phase 14 processed the six demo videos, seeded the registry, backed everything up (`scripts/backup.sh` / `scripts/restore.sh`) and wrote the demo-day runbook at the top of `README.md`; a cold start after `wsl --shutdown` was rehearsed following only that runbook. The pipeline's settings and thresholds are **frozen** as of Phase 7 (2026-11-06; the list is under "Acceptance run and frozen settings" in `ARCHITECTURE.md`): changing any of them means processing every demo video again, so do not tune them without the user asking. `PLAN.md` has the checklist.

**The footage changed on 2026-11-07:** the dashcam videos and the 2-minute pieces under `videos/clips/` were removed by the user and replaced with static-camera phone recordings in `videos/`. Anything in the docs that names `videos/clips/...` describes the old footage. **The demo set is three videos: `clear.mp4` (4K, 60 FPS), `rope.mp4` (4K, 30 FPS) and `zoomed-in.mp4` (1080p, 30 FPS).** The user does not want portrait (upright, phone-held-vertically) recordings: `portrait.mp4`, `portrait-new.mp4` and `portrait-narzo.mp4` were deleted by the user on 2026-11-07 and their results removed; never look for them, process them or add portrait footage back. The rotation handling in `probe_video` stays, because an upload could still be upright. Phase 14 cleared the old runs (`tracko-anpr reset-data --yes`) and processed the demo set; the database and `storage/` hold those three videos (plus `214173`, an upload processed on 2026-11-07), backed up under `backups/` (latest `20261107-062723`). On 2026-11-07 the render pass was made cheaper (item 4 "Faster Video Processing", step 1: plate boxes reused from stage 4, annotated copy at 1080p; the section with the measurements and the planned steps 2 and 3 is "FASTER VIDEO PROCESSING" in `ARCHITECTURE.md`) and the demo set was processed again with identical results: clear 667 s, rope 145 s, zoomed-in 208 s.

**The build follows `PLAN.md`:** 14 phases, done one at a time. Start a phase only on the user's go-ahead, never because the previous one finished. When a phase is done, say "Phase N of 14 complete — M phases left", list them, and stop. Tick the phase off in `PLAN.md`.

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
uv add <package>        # add a dependency (updates pyproject.toml and uv.lock)
uv run tracko-anpr process <video.mp4>                # the whole pipeline; results in storage/processed/<name>/
uv run tracko-anpr process <video.mp4> --max-seconds 20 --name smoke   # quick end-to-end check
uv run tracko-anpr track <video.mp4>                  # detect and track vehicles only; results in storage/processed/
uv run tracko-anpr track <video.mp4> --max-seconds 10 # same, first 10 seconds only (quick check)
uv run tracko-anpr track <video.mp4> --no-video       # detections and tracks only, no annotated video (faster)
uv run tracko-anpr read-plates <folder>               # read plate crops through the reader service (full round trip)
uv run tracko-anpr process <video.mp4> --no-db        # files only, no database rows
uv run tracko-anpr db-status                          # is the database up and migrated, and what is in it
uv run tracko-anpr enqueue <video.mp4 | id | name>    # queue a video for the worker (a new path is registered first)
uv run tracko-anpr ingest <video.mp4> [--name N]      # register a file already on disk without copying it
uv run tracko-anpr worker                             # run queued jobs until Ctrl+C; --once runs one job and exits
uv run tracko-anpr jobs                               # the queue: status, stage, progress, attempts, error
uv run tracko-anpr web                                # API + dashboard on http://localhost:8080 (docs at /api/docs)
uv run tracko-anpr seed-registry [--share 0.5] [--extra 4] [--reset]   # the FICTIONAL demo registry from recognized plates
uv run tracko-anpr reset-data --yes                   # delete every result, upload, crop and registry record (start over)
scripts/backup.sh / scripts/restore.sh backups/<stamp>  # database dump + storage archive, and putting them back
docker compose up -d                                  # start PostgreSQL (needs .env with POSTGRES_PASSWORD)
uv run alembic upgrade head                           # create or update the tables
uv run alembic revision --autogenerate -m "..."       # after changing db/models.py; read the file it writes
```

`process` needs the database up and migrated unless `--no-db` is given; it checks before starting the run. `.env` is created by copying `.env.example` and setting `POSTGRES_PASSWORD`; it is git-ignored and the password in it belongs to this machine's local container only. Keep `.env` with Unix line endings: Compose and the app's own reader tolerate CRLF, but a shell `source .env` does not.

`track` on a full 2-minute clip takes two and a half to seven minutes and `process` takes three and a half to eight and a half (measured on 2026-11-06 over one clip from each of the eight videos: 195 to 353 s at 1080p, 301 to 499 s at 2K; the tracking stage varies by about 20% between runs of the same clip), so run those in the background; the first frame alone takes several seconds while the GPU starts up. At those speeds the full-length videos take 7 minutes (`trafiic`) to 98 minutes (`kozhikode` at 2K), about 6 hours for all eight; the table is in `ARCHITECTURE.md`.

Run git with Windows git (PowerShell or Git Bash), not inside WSL. WSL's git reports about 50 untouched files as modified, and `git add .` from there would stage them all.

The OCR project has its own environment, so its commands run from inside `ocr/` (with the main environment active, uv prints a harmless `VIRTUAL_ENV` warning):

```bash
cd ocr
uv run anpr-ocr read <folder or image>   # read plate crops; add --json FILE to save the readings
uv run pytest                            # the OCR project's tests
```

`uv run ruff check` from the repo root lints both projects.

Python is pinned to 3.12 (`.python-version`); the build backend is `uv_build` with a `src/` layout.

The backend must run on FastAPI 0.162.0 exactly (`uv add "fastapi==0.162.0"` when it is first added). NiceGUI is built on FastAPI and shares that install, so pick a NiceGUI version whose FastAPI requirement allows 0.162.0.

Decisions made by the user (2026-11-06):

- **Database layer:** SQLAlchemy with Alembic migrations and the psycopg 3 driver.
- **Versions:** apart from FastAPI (0.162.0) and PostgreSQL (18), take the latest stable release at install time and rely on `uv.lock` to lock it. PyTorch and PaddlePaddle are the exception: their versions are constrained by the GPU driver (see Open dependencies).
- **Web app:** one process, with NiceGUI mounted on the FastAPI app. It must run as a single server process because NiceGUI keeps session state in memory. Splitting the dashboard and API into two services is listed in `ARCHITECTURE.md` as a future implementation; do not build it now, but keep dashboard code calling shared service functions so the split stays possible.
- **Build order:** pipeline first. Get one video through detection, tracking, plate detection and OCR from the command line before any database, API or dashboard work. The phases and their order are in `PLAN.md`. The OCR is smoke-tested before the plate detectors are compared, because "can the OCR read this crop" is how the plate detector gets chosen.
- **Who runs what:** Claude runs installs and system commands itself (`uv add`, `docker compose`, model downloads) and logs them in `ARCHITECTURE.md`. The one exception is downloading the PaddleOCR source, which is handed to the user as a command. Anything needing `sudo` is handed over too; never reuse a password from an earlier conversation.
- **Third-party weights:** never load a `.pt` from `pretrained-numberplate-weight/` in the main environment. They are scanned, then loaded only inside a Docker container with no network, and the chosen one is re-saved in a safe format before the application uses it.
- **Accuracy:** show recognition coverage and confidence only, labelled as not being accuracy. Measuring real accuracy against a hand-labelled set is a future implementation; the full procedure (sample size, label sheet columns, labelling rules, what to count, how to report) is the section "HOW TO MEASURE REAL ACCURACY" in `ARCHITECTURE.md`, and the labels go in `labels/` (empty so far). Follow it as written; do not show an accuracy figure on the dashboard before a label sheet exists.
- **Plate detector:** test the downloaded weights in `pretrained-numberplate-weight/` on the user's own clips first; fine-tune YOLO26s on the IURS-NPDS dataset (19,309 images) only if they miss plates.
- **Job hand-off:** the `processing_jobs` table in PostgreSQL is the queue. FastAPI inserts a queued row, the worker polls and claims it, writes stage and progress back, and must reset jobs left at "processing" by a crash when it starts.
- **Video input:** the pipeline takes MP4 only, at any resolution and frame rate; 1080p at 30 FPS is only the suggestion. Never hardcode 1920×1080 or 30: read both from each video and derive everything from them (timestamps, the tracker's lost-track buffer, chart buckets, box coordinates, the annotated output's size and frame rate). Clips in another container are converted to H.264 MP4 with FFmpeg beforehand, keeping their own resolution and frame rate. The source clips are in `videos/` (git-ignored): six 1080p MP4s at 29.97 to 60 FPS, plus `kochi.mp4` and `kozhikode.mp4`, which the user converted from the two 2K `.webm` files at 2560×1440 (`kochi.webm` has since been deleted). For long FFmpeg conversions the user prefers to be given the command and run it themselves; quick cuts they have asked Claude to run.
- **Test clips (superseded on 2026-11-07, kept for the record):** Phases 2 to 9 were built and measured on 2-minute pieces of eight dashcam videos under `videos/clips/<video>/<video>_partNN.mp4` (1080p at 29.97 to 60 FPS and 2560×1440 at 30 and 59.94 FPS). The user removed all of them on 2026-11-07; the six static-camera recordings now in `videos/` (see the status paragraph) are the test and demo footage from here on. FFmpeg 6.1.1 was installed in WSL with apt on 2026-11-06; system installs like this are logged under "System Setup — Installation Commands" in `ARCHITECTURE.md`, so add new ones there.
- **Vehicle classes:** four only (car, motorcycle, bus, truck). Auto-rickshaw support is a future implementation. The class is called "Motorcycle" everywhere, never "Bike".
- **Licence:** YOLO26 and weights trained from it are AGPL-3.0. Proceed with YOLO26 for the POC; the question is flagged in `ARCHITECTURE.md` to settle before production or customer use.
- **Demo registry:** fictional records are generated from a share of the plates recognized in the demo videos, so both matches and non-matches appear.
- **Dashboard:** the Overview has a video selector, and the five summary cards switch between the selected video and all videos. "Detections Over Time" counts new vehicles per 10-second bucket. Filled green backgrounds use dark green `#166522` with white text, not white on bright green. The header bell and profile icon are decorative: no login, no notifications.
- **Code quality:** Ruff for both linting and formatting, pytest for tests. Both are installed as dev dependencies and configured in `pyproject.toml`; the commands are `uv run ruff check`, `uv run ruff format`, `uv run pytest`, and `uv run pytest path/to/test_file.py::test_name` for a single test.

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

Ultralytics has TrackTrack built in — do not look for a fork or write a custom integration. It was added on 2026-06-09 (PR #24371), is in the current release (8.4.203, checked 2026-11-06) and is the default tracker in the official docs (https://docs.ultralytics.com/modes/track/). Use it through the normal tracking call with `tracker="tracktrack.yaml"`; copy that file from `ultralytics/cfg/trackers/` to customise it. Its defaults: camera motion compensation on (`gmc_method: sparseOptFlow`), lost tracks kept 30 frames (`track_buffer`), ReID off (`with_reid: False`). Its lost-track time is counted in frames with no frame-rate scaling, so it is set per video (`lost_track_buffer` in `pipeline/tracking.py`). Tracking also needs the `lap` package, which is in `pyproject.toml`. `tracko_anpr/__init__.py` sets `YOLO_AUTOINSTALL=False`, because Ultralytics otherwise installs missing packages behind uv's back and the next `uv sync` removes them; if Ultralytics reports a missing package, add it with `uv add`. For FP16, pass `quantize=16`; the older `half=True` still works in 8.4.203 but prints a deprecation warning on every call. Measured on 2026-11-06 over full 2-minute clips at input size 1536, FP16: detection and tracking run at about 48 frames per second on 1080p and 30 to 35 on 2K; with rendering, a whole run manages about 25 frames per second on 1080p and 16 to 18 on 2K. Peak memory for tracking alone was 350 MiB of GPU (PyTorch) and 2 GB of RAM; the whole `process` run peaks at 1.6 GB of GPU memory in the main process (the plate detector on a batch of 32 cut-outs), about 3.4 GB of GPU in all with the reader, and 2.2 to 2.5 GB of RAM (Phase 7 measurements).

How the pipeline code is organised (`src/tracko_anpr/pipeline/`):

- `video.py` reads a video's properties with ffprobe, yields frames with OpenCV, and writes H.264 MP4 by piping frames to FFmpeg (`FFmpegWriter`). Output goes to a `.part.mp4` name and is renamed only on success. Do not add `-shortest`: the clips' audio is a few milliseconds shorter than the video, and it cut frames off the end.
- `tracking.py` wraps YOLO26m and TrackTrack (`VehicleTracker`), runs the tracking pass (`track_video`) and keeps every frame's boxes in memory. `TrackRegistry` settles each track on one class by confidence-weighted vote.
- `annotate.py` draws boxes and labels and renders the annotated video as a second pass over the video, after tracking and validation, so labels use what is known about the whole track. Plates get an amber outline with the number below; a confirmed number is black on amber with its confidence, an unconfirmed one is amber on dark and says "unconfirmed". **The plate detector does not run in this pass** (since 2026-11-07): `plate_boxes_by_frame` places each outline from the stage-4 sightings, interpolating the plate's position relative to the vehicle box between the sighted frames and holding it outside them, so the outline can drift a little while a vehicle is partly hidden. **Inputs taller than 1080p are scaled down to 1080p for the annotated copy** (`PipelineOptions.annotated_max_height`; boxes scaled with the frame, `output_size` keeps the width even); the original video, the crops and every result stay at full resolution, and `tracko-anpr track` keeps the input size. Together these took the render pass of a 4K video from about half the run to a tenth.
- `results.py` writes the per-frame detections CSV and the per-track JSON.
- `rules.py` decides which tracks count as vehicles: followed at least 0.5 s and at some point at least 6% of the frame height tall, and not the camera car itself. The camera car has two shapes: its bonnet (10 s or longer, a quarter of the frame wide, on the bottom edge 80% of the time) and, when the camera is inside the cab (`ooty`, `truck`), its own door pillar and window boxed as a "car" (3 s or longer, at least 40% of the frame wide, with another vehicle's whole box inside it in 10% of its frames). Sizes are fractions and times are seconds, so nothing depends on resolution or frame rate.
- `validation.py` is plain logic, no model: plate formats, look-alike correction, and `decide`, which turns a vehicle's readings into Confirmed, Unconfirmed or Not Detected. The thresholds are in `ValidationRules`.
- `runner.py` is the whole pipeline (`run_pipeline`): the seven stages in order with a progress callback per stage (`STAGES` matches the dashboard timeline), per-stage timings, and the result files. It returns a `PipelineResult` whose `document` is the whole `results.json`. The worker in Phase 9 calls this; do not duplicate it.

The database layer (`src/tracko_anpr/db/`, Phase 8) is separate from the pipeline, which knows nothing about it:

- `models.py` has the seven tables as SQLAlchemy models (`videos`, `processing_jobs`, `vehicle_tracks`, `plate_observations`, `recognition_events`, `demo_registry`, `app_settings`) and the job status constants. JSON columns are `JSON().with_variant(JSONB, "postgresql")` so the tests run on SQLite; keep new JSON columns the same way.
- `store.py` maps a `PipelineResult` onto the tables: `register_video` (one `videos` row per file, by name), `create_job`, `store_result`, `mark_failed`. The command line and the worker both go through these.
- `metrics.py` defines every dashboard figure once, as queries over each video's **latest completed job** (`latest_completed_jobs`): `summary`, `category_breakdown`, `validation_breakdown`, `detections_over_time`, `detections`, `processing_durations`. Add new figures here, not in the API or the pages.
- `session.py`: `make_engine`, `session_scope`, `check_connection` (raises `DatabaseUnavailable` with a plain message), `current_revision`.
- `migrations/` is Alembic; `env.py` takes the URL from the project settings, so there is no password in `alembic.ini`. One revision so far (`fc32b7b47ec6`, the seven tables). Autogenerate misses renames and server defaults: read every generated file.
- A track's `counts_as_vehicle` (countable and not a repeat) is stored, not recomputed; Total Vehicles is a count of that column. A repeat track keeps its `recognition_events` row (its number) but is not counted.
- Three migrations so far: `fc32b7b47ec6` (the seven tables), `ba9303988888` (`processing_jobs.attempts`) and the `plate_corrections` table (2026-11-07).
- **Operator corrections never change the system's result.** `services/corrections.py` stores a correction (number and/or vehicle type, format-checked with `validation.is_valid_plate`) in `plate_corrections` beside the untouched `recognition_events` row; the newest per track is current, `undo_latest` removes it. `DetectionRow.correction` / `DetectionDetail.correction` carry it to the tables and the dialog, which show the corrected value with an amber pencil and the system's value in the tooltip. `metrics.py` ignores corrections by the user's decision: cards, coverage, registry matching and charts stay the pipeline's figures; Analytics has a separate "Operator Corrections" card. The export CSV carries `corrected_*` columns for the accuracy procedure. The operator's name is kept in the browser's `localStorage` (`tk_operator`), not on the server.

The worker (`src/tracko_anpr/worker/service.py`, Phase 9) is the only thing that runs the pipeline for the application; the web app never does:

- `Worker.start()` recovers jobs a dead worker left at `processing` (first time back to the queue with the half-written folders removed, second time failed), then `run_forever()` claims the oldest queued job with `FOR UPDATE SKIP LOCKED`, runs `run_pipeline` under the video's `name` with the worker's own long-lived reader, writes stage/progress/heartbeat on the job every 2 s, and ends it `completed` or `failed` (`"<ExceptionType>: <message>"`). One bad video never stops the worker.
- `run_pipeline(..., reader=...)` accepts a reader it does not own; the worker passes its own so the 20-second reader start-up is paid once per worker, not per job. The reader child is started with `PR_SET_PDEATHSIG`, so `kill -9` on the worker takes the reader with it.
- Ctrl+C once lets the current job finish; twice interrupts it and requeues it (attempts not counted). `--once` runs a single job, which is what the tests of the real pipeline use.
- The pipeline function and the reader factory are constructor parameters, so `tests/test_worker.py` exercises claiming, progress, failure and recovery with a fake pipeline on SQLite. `tests/result_builders.py` holds the shared fake `PipelineResult`.
- `enqueue` reuses a video's pending job instead of adding a second one. `ingest` registers a file where it lies (relative to the project root when inside it), for videos too large for a browser upload.
- **A damaged file must fail, not complete empty.** FFmpeg stops quietly where a file breaks, so a truncated MP4 once "completed" with 7 frames and no vehicles. `check_frames_read` in `runner.py` fails any run that decodes under 90% of the frames the header declares (`MIN_FRAMES_READ_SHARE`); do not remove it to make a bad file "work".

The web app (Phase 10): `tracko-anpr web` runs `api/app.py:create_app()` under uvicorn, FastAPI with NiceGUI mounted by `dashboard/app.py:mount_dashboard` (`ui.run_with`). Rules that keep it sound:

- **Routes and pages are thin; the logic lives in `services/`** (`videos`, `jobs`, `results`, `analytics`, `registry`, `app_settings`, `readiness`, `files`), which take a `Session` and return dataclasses. A dashboard page must call these, never the database or the files directly, so the dashboard could later become a separate process talking to the API.
- `create_app(settings, engine, dashboard=False)` is what the tests build, on SQLite with a temporary root (`tests/test_api.py`); the real app takes everything from `.env`.
- Files are served only from under `storage/` (`services/files.py`); crops only from the two crop folders. Videos go out through `FileResponse`, which answers `Range` requests with 206 so the player can seek. Do not replace it with a streaming response that ignores ranges.
- Uploads are `.mp4` only and are probed with ffprobe after writing; a bad file is deleted and the answer is 400 with the reason. The web process never runs the models: `POST /api/videos/{id}/process` only queues a job.
- `/api/system/status` is the sidebar panel's source. The worker writes an idle heartbeat into `app_settings` (`worker_heartbeat`) on every poll; the check is "reported within 15 s" when idle and within 60 s while on a job (progress reports pause for the reader's start-up and for plate batches; Phase 14 saw the panel flicker amber before this allowance). Never show green without it.
- `services/app_settings.py` shows the frozen pipeline settings and stores changes from the Settings page, but **a stored value is not applied to processing** (`applies_to_processing` is false on everything); the page is informative in the POC. Decide with the user in Phase 13 before making anything editable for real.
- Phone recordings held upright carry a `rotate -90` tag; `probe_video` swaps width and height for it (`stream_rotation`, `is_quarter_turn`), because OpenCV hands over upright frames. 4K decoding is CPU-bound: 5 to 10 frames/s in detection and tracking against 30 to 50 at 1080p/2K.

The dashboard (`src/tracko_anpr/dashboard/`, Phase 11 onwards):

- `layout.py:frame(active, title, subtitle)` wraps every page: it applies the theme (`ui.colors` with the green/amber palette, so Quasar's blue defaults never appear; `ui.dark_mode`), the header, the sidebar with the status panel, and yields the content column. Every page is `with frame(...)`. Nav items and routes are `NAV_ITEMS`.
- **The Tracko logo** (added by the user on 2026-11-07) lives as brand originals in `DESIGN/logo/full.png` and `half.png`: navy and blue on solid white, which the design forbids on screen. `tools/make_logo_assets.py` derives the served copies in `dashboard/static/logo/` (`logo-full.png` for the header, `mark.png` for the watermarks and narrow screens, `favicon.png`): white made transparent, the car body light, the blue brackets and arcs in the theme greens — the user's decision. Re-run it with `uv run python tools/make_logo_assets.py` if the originals change; never serve the originals. The header shows the full logo with "Vehicle ANPR POC" beside it; below 900 px the mark alone. `.tk-player-empty::before` paints the mark as a faint watermark behind every empty state.
- **All colours live in `static/theme.css`** (the tokens from DESIGN §18, served at `/dashboard-static/theme.css` with the Inter font files beside it, OFL licence included). Use the `tk-*` classes and CSS variables; never put a colour in Python. Filled green surfaces are dark green `#166522` with white text (`tk-primary`, `tk-banner.green`, active segment).
- `runtime.query(fn, *args)` is how a page calls a service: it opens a session in a thread and returns the result. Pages never import the database or open files.
- `components/status_panel.py` polls `readiness.system_status` every 5 s: green "System Ready" only when the database, a worker, the models, the reader and FFmpeg are all there; otherwise amber "Attention needed" with the failing checks named. The first render is a neutral "Checking…".
- `components/timeline.py` draws the seven stages from a `JobStatus` (done / running with counts / pending / failed) with the banner above; `components/player.py` is `VideoPlayer` (Original / Annotated switch that keeps the playback position via JavaScript, `seek()` for table rows).
- `pages/upload.py`: the upload goes through `videos.check_upload_name` → `FileUpload.save()` into `storage/uploads/.incoming/` → `videos.adopt_upload` (same ffprobe check and naming as the API). "Process Video" calls `jobs.start_processing`; a 1-second `ui.timer` redraws the timeline from `jobs.get_job` until the job ends. Nothing is simulated.
- `RECORDING_GUIDE.md` (project root) is the single source of recording advice (plate ≥130 px, ≤30°, 1080p@30, lock focus, light at the camera at night) with our measured read rates by plate width; `pages/upload.py:recording_tips()` renders its sections 1 to 3 in an expansion on the Upload page. Keep its figures in step with the acceptance measurements. The origin and the list of other Axis-inspired items are under "FEATURES INSPIRED FROM AXIS COMMUNICATIONS" in `ARCHITECTURE.md`.
- `pages/overview.py` is thin: all its data comes from `services/overview.py:overview(session, video_id, scope)` in one call, which `tests/test_db.py` checks against the metric queries. Charts are `ui.echart` (ECharts ships with NiceGUI, offline) in the design's colours; tables are plain HTML (`tk-html-table`) so rows can carry icons, badges and thumbnails. `components/detection_dialog.py:show_detection(track_pk)` is the shared details dialog (crops, evidence, registry match) that History reuses; `format.py` holds the shared formatters.
- **Give every `ui.button` `color=None`.** NiceGUI's default colour adds Quasar's `bg-primary` class, which wins over the theme's classes whatever their specificity (seen in Phase 12: segmented controls and primary buttons came out bright green). With `color=None` the `tk-primary`, `tk-secondary`, `tk-link` and `tk-segmented` classes style the button.
- The other pages: `pages/analysis.py` (player at full width, downloads, all tracked vehicles; `?t=` seeks on arrival), `pages/history.py` (filters, sort and paging are URL parameters, so every view has a link; Export CSV goes through the API), `pages/registry.py` (banner, lookup, recognised numbers vs registry, the records), `pages/analytics.py`, `pages/settings.py` (informative only; the settings are frozen). `components/detections_table.py` is the shared table. The registry seeder is `services/registry_seed.py`: deterministic, a share of confirmed numbers plus a few unseen ones, every field invented.
- **Create `ui.timer`s (and anything else that needs a slot) when the page is built, not inside event handlers.** A handler runs in the context of the element that fired it; if the handler redraws that element away first, creating a timer afterwards raises "The parent element this slot belongs to has been deleted" and the page silently stops updating (found in Phase 11). Make timers at build time with `active=False` and `activate()`/`deactivate()` them. Redraw cards with an explicit `with card:`.
- In a `signal` handler never `print()`: `pkill` delivers SIGTERM twice (through `uv` and directly) and `print` is not re-entrant. The worker's handler uses `os.write` and ignores a repeat SIGTERM.
- **Browser checks:** the Claude-in-Chrome extension on this machine cannot reach `localhost:8080` (ERR_CONNECTION_REFUSED, while PowerShell gets 200), so visual checks are done with headless Chromium through Playwright installed in a scratch venv on the Windows side (`python -m venv ...; pip install playwright; playwright install chromium`), which reaches the WSL server at `http://localhost:8080`. Headless Chrome's `--screenshot` flag is not enough: NiceGUI pages fill in over a websocket after load.

Things learned building the full pipeline (Phase 6, 2026-11-06) that are easy to undo by mistake:

- **Short plate numbers are real.** `KL39P77`, `KL361375`, `TN062264` and `KL452960` looked like misreadings and were all correct when checked against the plate images. The format check allows 0 to 3 series letters and 1 to 4 digits on purpose; do not tighten it.
- **A plate belongs to the smallest vehicle box containing its centre** (`plate_owner` in `runner.py`). Vehicle boxes overlap in traffic, so a van's cut-out showed the plate of the car ahead and both got that car's number confirmed. The same rule is applied when the renderer outlines plates. All plates found in a cut-out are considered, not just the most confident one.
- **Two tracks in view at the same time cannot both hold one confirmed number** (`settle_shared_numbers`); the one with fewer agreeing frames becomes unconfirmed. Two tracks with the same confirmed number at different times are the same vehicle under a new track id (`mark_repeat_tracks`): the later one keeps its number but is not counted again.
- Series letters never include I or O, which is what lets `KL1OAB1234` be corrected to `KL10AB1234`. A correction that could go two ways (`0D` as `OD` or `DD`) is refused, not guessed.
- Each vehicle is examined in up to 6 frames (`best_frames`), read with `read_selected_frames` so only those frames are decoded.
- Running `process` on a video again replaces that video's result folders.
- **Zero or low coverage on a clip is usually the plates, not the code.** `truck_part02` confirmed nothing: its median plate was 38 px wide and 78% were under 60 px, where the reader almost never succeeds. Check `plates.csv` plate widths before suspecting the pipeline.
- `results.json` records memory with `memory_peaks()` in `runner.py`, read at the end of the run so it covers every model loaded; the `track` command uses the same function.

The plate reader (`ocr/src/anpr_ocr/recognizer.py`) deliberately departs from Awiros's reference `test.py`; do not "fix" it back. Tested on 2026-11-06 against plates read by eye ("OCR Smoke Test" in `ARCHITECTURE.md`):

- It uses the model's attention (NRTR) decoder. The reference script's CTC decoder drops a character on almost every two-line plate, even on Awiros's own samples. The model's forward pass returns only the CTC branch outside training, so the recognizer calls both heads on the backbone features itself and returns the CTC text as a second opinion.
- It widens the plate image by 1.5 before reading, which stops characters at the right edge being lost.
- With both, all 16 clearly legible plates from our clips were read correctly (13 one-line, 3 two-line), against 11 for the reference method. That is a small sample: it justifies the method, not an accuracy claim.
- The model answers `UNREADBLE` (its spelling) for plates it cannot read; the recognizer turns that into an empty reading with `unreadable=True`.
- Confidence is not correctness. Good readings sit near 0.92, but on non-plates the attention decoder still writes a plausible plate number at about 0.2 to 0.3, and one Kerala plate was read as `DL...` at 0.86. Validation must apply a confidence threshold and vote across frames.
- Plate width decides success: under 60 px only about 12% of crops gave a confident plate-shaped reading, at 150 px and over about 68%. Prefer the frames where a vehicle is largest.
- Reading takes about 10 ms per plate after about 15 s of model loading, so keep one recognizer alive.

How the main program reaches the reader (Phase 5): `OcrClient` in `pipeline/ocr_client.py` starts `ocr/.venv/bin/anpr-ocr serve` as a child process and exchanges one JSON line per message over its standard input and output, passing plate crops as file paths. The protocol is documented in `ocr/src/anpr_ocr/service.py` and `ocr/README.md`.

- The client never waits forever: start-up and each request have time limits (`TRACKO_OCR_START_TIMEOUT`, `TRACKO_OCR_REQUEST_TIMEOUT`), and a dead reader is raised as `OcrError` with its exit code and last messages. After a death, the next `read()` starts a fresh reader by itself.
- Measured: about 20 s to start, then 8 to 10 ms per plate. A reader killed mid-request takes about 13 s to be reported, because WSL is slow to release a GPU process; that is not a hang.
- The service's standard output carries protocol messages only. `service.py` redirects everything else to standard error at the file-descriptor level, because PaddlePaddle prints from C++ as well as Python. Never `print()` to standard output in the OCR service.
- The client sets `LD_LIBRARY_PATH=/usr/lib/wsl/lib` for the reader, which removes PaddlePaddle's `libcuda.so` warning.
- GPU memory with YOLO26m (a 2K frame at input 1536), the plate detector and the reader all loaded: about 3.8 GB of 16 GB.
- `tests/test_ocr_client.py` runs the client against `tests/fake_ocr_service.py`, a stand-in that speaks the protocol and can be told to misbehave, so those tests need no model.

Plate detector comparison (Phase 4, run 2026-11-06; full write-up in `tools/plate_detector_eval/RESULTS.md`):

- All 14 candidates were scanned without loading (clean) and then run only inside the `tracko-plate-sandbox` Docker image with `--network none`. The tools and the exact commands are in `tools/plate_detector_eval/`.
- On 917 crops of 476 vehicles from all eight videos, the five leading candidates are equivalent: each led to a confident plate reading on 87 to 92 vehicles. **The user chose `sentry-26s`** (`ayannotfound__Sentry/best.pt`, YOLO26s at 640, made for vehicle crops), with no fine-tuning.
- The application loads only the safely re-saved copy in `models/plate/` (`sentry-26s.safetensors` + `.yaml` + `.json`), through `PlateDetector` in `pipeline/plates.py`, which refuses a `.pt` file. On the GPU at FP16 it matched the original's sandbox detections on 916 of 917 crops and takes 4.8 ms per vehicle crop. Never load anything from `pretrained-numberplate-weight/` in the main environment.
- `PlateDetector` rebuilds the network from the saved layout and passes that layout to Ultralytics as a dictionary. Given a file path instead, Ultralytics guesses the model size from the file name and silently builds the wrong size; keep it a dictionary.
- Reading, not finding, is the limit: some candidate drew a box on 443 of 476 vehicles but only 108 were ever read. Boxes under 60 px wide are almost never read. The same footage read twice as many vehicles at 2K as at 1080p.
- Most tracked vehicles never show a readable plate (side views, cut off by the frame edge), so low coverage on dashcam footage is expected, not a bug.
- The camera car's own bonnet (`trafiic`) or cab interior (`ooty`, `truck`) gets tracked as a vehicle. `is_camera_car` in `pipeline/rules.py` excludes both shapes; checked on all three videos in Phase 7 (it removed exactly the cabin tracks, 7 in `ooty_part03` and 8 in `truck_part02`, and no real vehicle). Every cabin track was at least 43% of the frame wide and no real vehicle in the eight clips more than 33%, which is where the 40% threshold comes from.
- `pipeline/cropping.py` holds `crop_region` (copies original pixels, never resizes) and `best_frames` (the frames where a track's box is largest and not cut off). Use `best_frames` to decide where to look for plates.

Passes are sequential on purpose (track, find plates, read, validate, render), matching the seven-stage timeline in the design. Anything that needs PyTorch is imported inside the function that uses it, so the tests run without loading a model.

Rules from the specs that are easy to break:

- Plate and vehicle crops must come from the original full-resolution frame, never from the resized inference frame.
- Track IDs are local to one processing job. Identify a track by job/video id plus track id, and never present it as a permanent vehicle identity.
- A plate is shown as confirmed only after multi-frame validation; otherwise it is pending or unconfirmed.
- "Recognition coverage" is validated plates ÷ eligible tracked vehicles. Do not label it, or confidence averages, as accuracy.
- The demo registry is fictional data and must be labelled as such; there is no real registration lookup.
- Mock dashboard data must be labelled "Demo Data" and kept separate from real API responses. Never show fake progress or fake completed results.
- Video files live on disk under `storage/`; PostgreSQL stores only references.
- Out of scope: RTSP, WebRTC, live cameras, Redis/Celery, cloud services, microservices, React, model training in the dashboard.

## Open dependencies

These are assumed by the specs but not yet confirmed or available:

- The plate detector is `sentry-26s`, chosen by comparison (see the Phase 4 notes above). Its weaknesses are known and accepted for the POC: 10 epochs of training on mixed data, and no licence file in its repository. Fine-tuning our own YOLO26s on IURS-NPDS was judged unnecessary on the evidence and is not planned.
- `Awiros/anpr-ocr` on Hugging Face is public, ungated and Apache-2.0; `model.safetensors` (149 MB) downloads without login (checked 2026-11-06). It is not a pip-installable pipeline: its `test.py` builds the network from the PaddleOCR source tree (`ppocr`, cloned from GitHub) and loads the safetensors into it, so the project needs a pinned PaddleOCR checkout plus `paddlepaddle-gpu>=2.6.0`. Input is a plate crop resized to 48 px high (max 320 wide); output is uppercase text plus a CTC confidence. Accuracy figures are the publisher's own. The source is checked out at `ocr/vendor/PaddleOCR` (tag `v3.7.0`), and on 2026-11-06 the network it builds matched the weights exactly (545 of 545 tensors) on the GPU with the packages already in `ocr/pyproject.toml`. Plate crops are now read correctly (see the reader notes under "Planned architecture"). The source prints harmless `SyntaxWarning` lines on import, and PaddlePaddle prints a `libcuda.so` message that has not affected GPU use so far.
- PyTorch and PaddlePaddle clash in one environment (resolution tested on 2026-11-06; both are now installed, each in its own environment):
  - The NVIDIA driver is 572.16, which reports CUDA 12.8. PyPI's default `torch` (2.15.0) is built against CUDA 13 libraries and probably needs a newer driver; the newest CUDA 12.6 build is `torch==2.14.1+cu126` from `https://download.pytorch.org/whl/cu126`.
  - GPU builds of PaddlePaddle 3.x come from Paddle's own index (`https://www.paddlepaddle.org.cn/packages/stable/cu126/`, latest 3.3.1), not PyPI. PyPI only has the old 2.6.2, which uv silently falls back to.
  - `torch==2.14.1+cu126` pins `nvidia-cudnn-cu12==9.10.2.21` and `paddlepaddle-gpu==3.3.1` pins `==9.5.1.17`, so uv cannot resolve them together.
  - **Decision (user, 2026-11-06): keep the current driver, no upgrade.** The main environment uses `torch==2.14.1+cu126` (not the PyPI default). The OCR runs in its own uv project with its own `.venv` (`paddlepaddle-gpu==3.3.1`, CUDA 12.6 build, plus a pinned PaddleOCR source checkout) and as a separate process that the worker sends plate crops to. That project is `ocr/` at the repo root (package `anpr_ocr`, created with `uv init --no-workspace` so it is not a workspace member and has its own lock file); the PaddleOCR source goes in `ocr/vendor/`. Run its commands from inside `ocr/`. Never add PaddlePaddle to the main `pyproject.toml`, and never make `ocr/` a uv workspace member.

## Repository notes

- Main package `src/tracko_anpr/` has `config.py` (settings from `.env` and the environment), `cli.py` (the `tracko-anpr` command: `process`, `track`, `read-plates`, `db-status`, `worker`, `enqueue`, `ingest`, `jobs`, `web`), the `pipeline`, `db`, `worker`, `services` and `api` packages described above, and `dashboard` (`app.py` mounts NiceGUI; `layout.py`, `runtime.py`, `components/`, `pages/`, `static/`). `migrations/`, `alembic.ini` and `docker-compose.yml` are at the project root.
- `models/` holds what the app loads and is git-ignored apart from `.gitkeep`: `yolo26m.pt` (official Ultralytics release), `plate/` (the safely re-saved plate detector) and `awiros/` (the OCR model, its dictionary and its reference `test.py`). Sources and checksums are recorded in `ocr/README.md`.
- `storage/` holds uploads and generated files, also git-ignored apart from `.gitkeep`.
- Commits are staged with `git add .`, so `.gitignore` is the only thing keeping large or secret files out. It covers `videos/`, model weights, `runs/` and `datasets/` (Ultralytics output), `.env`, and the vendored PaddleOCR source. Add a rule there before creating any new kind of generated file.
- WSL sees 15 GB of the machine's 32 GB RAM (no `.wslconfig`). Two model processes, PostgreSQL and 2K frames share it; raising the limit is the user's change to make.
- The folder is `DESIGN/` (uppercase); mind the case when working from WSL.
