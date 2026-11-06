# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Offline proof of concept for Indian vehicle detection, tracking and number plate recognition (ANPR) on uploaded MP4 videos, shown through a dashboard for a leadership demo. It is not a live-camera system.

**Status: Phases 1 to 6 of 14 are done.** Both Python environments are installed and see the GPU, the model files are in `models/`, and one command runs a video through the whole pipeline from the command line (`tracko-anpr process`): vehicle detection and tracking, plate detection, plate reading through the reader service, validation across frames, and the annotated video. Results are files under `storage/`. The acceptance run and freeze (Phase 7), the database, the worker, the API and the dashboard do not exist yet. `PLAN.md` has the checklist.

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
```

`track` on a full 2-minute clip takes two and a half to seven minutes and `process` takes six to ten (measured on 2026-11-06: 372 to 429 s for 1080p at 60 FPS, 484 to 586 s for 2K at 59.94 FPS), so run those in the background; the first frame alone takes several seconds while the GPU starts up. More than half of the rendering time in `process` goes on finding each plate again in every frame to outline it.

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
- **Accuracy:** show recognition coverage and confidence only, labelled as not being accuracy. Measuring real accuracy against a small hand-labelled set is a future implementation.
- **Plate detector:** test the downloaded weights in `pretrained-numberplate-weight/` on the user's own clips first; fine-tune YOLO26s on the IURS-NPDS dataset (19,309 images) only if they miss plates.
- **Job hand-off:** the `processing_jobs` table in PostgreSQL is the queue. FastAPI inserts a queued row, the worker polls and claims it, writes stage and progress back, and must reset jobs left at "processing" by a crash when it starts.
- **Video input:** the pipeline takes MP4 only, at any resolution and frame rate; 1080p at 30 FPS is only the suggestion. Never hardcode 1920×1080 or 30: read both from each video and derive everything from them (timestamps, the tracker's lost-track buffer, chart buckets, box coordinates, the annotated output's size and frame rate). Clips in another container are converted to H.264 MP4 with FFmpeg beforehand, keeping their own resolution and frame rate. The source clips are in `videos/` (git-ignored): six 1080p MP4s at 29.97 to 60 FPS, plus `kochi.mp4` and `kozhikode.mp4`, which the user converted from the two 2K `.webm` files at 2560×1440 (`kochi.webm` has since been deleted). For long FFmpeg conversions the user prefers to be given the command and run it themselves; quick cuts they have asked Claude to run.
- **Test clips:** build and test the pipeline on the 2-minute pieces in `videos/clips/<video>/<video>_partNN.mp4`, one folder per video (82 pieces across eight videos, cut on 2026-11-06 without re-encoding). They cover 1080p at 29.97, 30, 50 and 60 FPS and 2560×1440 at 30 and 59.94 FPS. Pieces are about 120 seconds but vary by a few seconds, and the last piece of each video is shorter. `clips/kozhikode/` (2K) and `clips/kozikode-4k/` (1080p) are the same footage at two resolutions. The full videos (5 to 41 minutes) are for the final demo. FFmpeg 6.1.1 was installed in WSL with apt on 2026-11-06; system installs like this are logged under "System Setup — Installation Commands" in `ARCHITECTURE.md`, so add new ones there.
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

Ultralytics has TrackTrack built in — do not look for a fork or write a custom integration. It was added on 2026-06-09 (PR #24371), is in the current release (8.4.203, checked 2026-11-06) and is the default tracker in the official docs (https://docs.ultralytics.com/modes/track/). Use it through the normal tracking call with `tracker="tracktrack.yaml"`; copy that file from `ultralytics/cfg/trackers/` to customise it. Its defaults: camera motion compensation on (`gmc_method: sparseOptFlow`), lost tracks kept 30 frames (`track_buffer`), ReID off (`with_reid: False`). Its lost-track time is counted in frames with no frame-rate scaling, so it is set per video (`lost_track_buffer` in `pipeline/tracking.py`). Tracking also needs the `lap` package, which is in `pyproject.toml`. `tracko_anpr/__init__.py` sets `YOLO_AUTOINSTALL=False`, because Ultralytics otherwise installs missing packages behind uv's back and the next `uv sync` removes them; if Ultralytics reports a missing package, add it with `uv add`. For FP16, pass `quantize=16`; the older `half=True` still works in 8.4.203 but prints a deprecation warning on every call. Measured on 2026-11-06 over full 2-minute clips at input size 1536, FP16: detection and tracking run at about 48 frames per second on 1080p and 30 to 35 on 2K; with rendering, a whole run manages about 25 frames per second on 1080p and 16 to 18 on 2K. Peak memory was 350 MiB of GPU (PyTorch) and 2 GB of RAM.

How the pipeline code is organised (`src/tracko_anpr/pipeline/`):

- `video.py` reads a video's properties with ffprobe, yields frames with OpenCV, and writes H.264 MP4 by piping frames to FFmpeg (`FFmpegWriter`). Output goes to a `.part.mp4` name and is renamed only on success. Do not add `-shortest`: the clips' audio is a few milliseconds shorter than the video, and it cut frames off the end.
- `tracking.py` wraps YOLO26m and TrackTrack (`VehicleTracker`), runs the tracking pass (`track_video`) and keeps every frame's boxes in memory. `TrackRegistry` settles each track on one class by confidence-weighted vote.
- `annotate.py` draws boxes and labels and renders the annotated video as a second pass over the video, after tracking and validation, so labels use what is known about the whole track. Plates get an amber outline with the number below; a confirmed number is black on amber with its confidence, an unconfirmed one is amber on dark and says "unconfirmed".
- `results.py` writes the per-frame detections CSV and the per-track JSON.
- `rules.py` decides which tracks count as vehicles: followed at least 0.5 s and at some point at least 6% of the frame height tall, and not the camera car's own bonnet (10 s or longer, wide, on the bottom edge 80% of the time). Sizes are fractions and times are seconds, so nothing depends on resolution or frame rate.
- `validation.py` is plain logic, no model: plate formats, look-alike correction, and `decide`, which turns a vehicle's readings into Confirmed, Unconfirmed or Not Detected. The thresholds are in `ValidationRules`.
- `runner.py` is the whole pipeline (`run_pipeline`): the seven stages in order with a progress callback per stage (`STAGES` matches the dashboard timeline), per-stage timings, and the result files. The worker in Phase 9 calls this; do not duplicate it.

Things learned building the full pipeline (Phase 6, 2026-11-06) that are easy to undo by mistake:

- **Short plate numbers are real.** `KL39P77`, `KL361375`, `TN062264` and `KL452960` looked like misreadings and were all correct when checked against the plate images. The format check allows 0 to 3 series letters and 1 to 4 digits on purpose; do not tighten it.
- **A plate belongs to the smallest vehicle box containing its centre** (`plate_owner` in `runner.py`). Vehicle boxes overlap in traffic, so a van's cut-out showed the plate of the car ahead and both got that car's number confirmed. The same rule is applied when the renderer outlines plates. All plates found in a cut-out are considered, not just the most confident one.
- **Two tracks in view at the same time cannot both hold one confirmed number** (`settle_shared_numbers`); the one with fewer agreeing frames becomes unconfirmed. Two tracks with the same confirmed number at different times are the same vehicle under a new track id (`mark_repeat_tracks`): the later one keeps its number but is not counted again.
- Series letters never include I or O, which is what lets `KL1OAB1234` be corrected to `KL10AB1234`. A correction that could go two ways (`0D` as `OD` or `DD`) is refused, not guessed.
- Each vehicle is examined in up to 6 frames (`best_frames`), read with `read_selected_frames` so only those frames are decoded.
- Running `process` on a video again replaces that video's result folders.

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
- The camera car's own dashboard and bonnet get tracked as a vehicle in some videos (`ooty`, `truck`). `is_camera_car` in `pipeline/rules.py` excludes it; it has unit tests but has not yet been run on those two videos (Phase 7 does).
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

- Main package `src/tracko_anpr/` has `config.py` (settings from `.env` and the environment), `cli.py` (the `tracko-anpr` command: `process`, `track`, `read-plates`), the `pipeline` package described above, and still-empty subpackages `api`, `dashboard` (`components`, `pages`), `db` and `worker`. `migrations/`, `alembic.ini` and `docker-compose.yml` are not created yet.
- `models/` holds what the app loads and is git-ignored apart from `.gitkeep`: `yolo26m.pt` (official Ultralytics release), `plate/` (the safely re-saved plate detector) and `awiros/` (the OCR model, its dictionary and its reference `test.py`). Sources and checksums are recorded in `ocr/README.md`.
- `storage/` holds uploads and generated files, also git-ignored apart from `.gitkeep`.
- Commits are staged with `git add .`, so `.gitignore` is the only thing keeping large or secret files out. It covers `videos/`, model weights, `runs/` and `datasets/` (Ultralytics output), `.env`, and the vendored PaddleOCR source. Add a rule there before creating any new kind of generated file.
- WSL sees 15 GB of the machine's 32 GB RAM (no `.wslconfig`). Two model processes, PostgreSQL and 2K frames share it; raising the limit is the user's change to make.
- The folder is `DESIGN/` (uppercase); mind the case when working from WSL.
