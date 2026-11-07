# tracko-anpr

Proof of concept for Indian vehicle detection, tracking and number plate recognition (ANPR) on uploaded MP4 videos. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design and [PLAN.md](PLAN.md) for the build plan and progress.

## Demo day: starting the system from cold

Everything runs inside WSL (Ubuntu 24.04). Open a WSL terminal (`wsl` in PowerShell) and go to the project:

```bash
cd /mnt/c/Users/ontashai/Desktop/tracko-anpr
```

1. **Database.** The PostgreSQL container restarts by itself when WSL starts. Check, and start it if it is not there:

   ```bash
   docker compose ps                 # should say "healthy"; if nothing is listed:
   docker compose up -d && sleep 5 && docker compose ps
   uv run alembic upgrade head       # no-op when the tables are current
   ```

2. **Worker** (its own terminal; it stays in the foreground and prints what it does):

   ```bash
   uv run tracko-anpr worker
   ```

   The first job after a start takes about 20 seconds longer while the plate reader loads, and the first plate-size check about 30 seconds longer while its two detectors load.

3. **Web app** (a second terminal):

   ```bash
   uv run tracko-anpr web
   ```

4. **Browser.** On the Windows side open **http://localhost:8080/** (WSL forwards localhost). The status panel at the bottom of the sidebar must say **System Ready** in green. If it says "Attention needed", it names what is missing: usually the worker (step 2) or the database (step 1).

   Health check without a browser: `curl -s http://localhost:8080/api/system/status` — `"ready": true`.

5. **Check the demo data is there:** `uv run tracko-anpr db-status` lists the videos, jobs and the overall figures. The Overview should open on `kdy`, the main demo video (125 vehicles, 3 confirmed plates). Its selector also lists `clear` and `zoomed-in`, which are kept but no longer used (369 vehicles and 49 confirmed plates across all three). If the data is gone, restore the last backup (below) — do not reprocess on the day; a 4K video takes 2.5 to 11 minutes, a 1080p one about twice its length.

How long it takes (rehearsed 2026-11-07 from `wsl --shutdown`): the container is back on its own within 10 seconds of the first WSL command, the worker is ready a few seconds after it is started, and the status API says ready as soon as the web app is up; the whole cold start is under a minute. A restore takes about 15 seconds. A live upload of a 20-second 1080p clip showed its plate-size verdict after 50 seconds (cold worker) and finished processing 70 seconds after "Process Video".

**Recording new videos:** follow [RECORDING_GUIDE.md](RECORDING_GUIDE.md) — plate at least 130 px wide, camera in line with the traffic, 1080p at 30 fps. It is the biggest lever on how many plates get read.

Nothing on any page is fetched from the internet (fonts, charts and icons are served by the app), so the demo works with the network unplugged. The database does not need the network either.

Stopping: Ctrl+C in each terminal (the worker finishes its current job first; Ctrl+C again interrupts it), and `docker compose down` only if the container should stop too — the data stays.

### Backup and restore

```bash
scripts/backup.sh                      # -> backups/<date-time>/ (database dump + storage archive)
scripts/restore.sh backups/<date-time> # replaces the database and storage/ with that backup
```

Stop the worker and the web app before restoring. The source videos in `videos/` are not part of the backup: keep that folder. `backups/` is git-ignored. If a restore ever fails, `uv run tracko-anpr reset-data --yes` empties everything and the videos can be queued again with `uv run tracko-anpr enqueue videos/<name>.mp4`.

### If something is wrong on the day

| Symptom | What to do |
|---|---|
| Status panel: "worker … has probably stopped" | Start the worker (step 2). |
| Status panel: database not reachable | `docker compose up -d`; wait for "healthy". |
| Status panel: database not migrated | `uv run alembic upgrade head`. |
| Browser cannot reach localhost:8080 | Is `tracko-anpr web` running? Try `http://127.0.0.1:8080/`; failing that, the WSL address from `hostname -I` inside WSL. |
| An upload stays "Queued" | The worker is not running, or is busy with an earlier job; `uv run tracko-anpr jobs` shows the queue. |
| A job is "Failed" | The reason is on the Upload page and in `uv run tracko-anpr jobs`; a damaged file says so. |
| The plate-size check stays at "waiting for the worker" | The worker is not running (step 2); it serves checks before jobs, so a running worker answers within a minute. |

## Usage

Run from the project root, in WSL.

### Process a video from start to finish

```bash
uv run tracko-anpr process videos/zoomed-in.mp4
```

This runs the whole pipeline over an MP4: vehicle detection and tracking, plate detection, plate reading, validation across frames, and the annotated video. It prints each stage as it goes, then a summary: tracks, vehicles by type, how many number plates were confirmed, unconfirmed or not detected, recognition coverage (which is not accuracy), and the confirmed numbers.

Results go under `storage/`, in folders named after the video:

- `storage/processed/<name>/annotated.mp4` — the video with every vehicle boxed and labelled, plates outlined in amber, and each number shown as confirmed (`KL10AB1234 (0.97)`) or `unconfirmed`. Same frame rate and frame count as the input, with the original audio; inputs above 1080p are scaled down to 1080p for playback (the original video is untouched).
- `storage/processed/<name>/results.json` — one record per track (type, when it was seen, plate decision and the reason for it), plus the summary, timings and settings.
- `storage/processed/<name>/detections.csv` — one row per vehicle per frame.
- `storage/processed/<name>/plates.csv` — one row per plate examined, with what the reader made of it.
- `storage/vehicle_crops/<name>/` and `storage/plate_crops/<name>/` — the cut-out images.

The run is also recorded in the database (see "Database" under Setup): a `videos` row for the file, a `processing_jobs` row for this run, and one row per track, plate examined and plate decision. `uv run tracko-anpr db-status` shows what is stored and the overall figures.

Options: `--max-seconds N` processes only the first N seconds; `--no-video` skips the annotated video; `--name NAME` chooses the folder name; `--no-db` writes files only. `uv run tracko-anpr check <video.mp4>` runs only the plate-size check (24 sampled frames, about half a minute) and says whether the plates are big enough to read, without processing anything. Processing the same video again replaces its earlier result files and adds a new job to the same video; the dashboard shows the latest.

A 2-minute clip takes about three and a half minutes at 1080p and up to eight and a half at 2K; a full-length video takes roughly two to four times its own length (the table is under "Acceptance run and frozen settings" in `ARCHITECTURE.md`). The rules that decide what counts as a vehicle and when a number is confirmed are in section 10 of `ARCHITECTURE.md`, and the settings are frozen as of Phase 7.

### Process videos through the worker

The application processes videos in a separate worker process, fed by a queue in the database. From the command line the same path is:

```bash
uv run tracko-anpr enqueue videos/zoomed-in.mp4   # register the file and queue it
uv run tracko-anpr worker                                        # run queued jobs until Ctrl+C
uv run tracko-anpr jobs                                          # what is queued, running, done or failed
```

`enqueue` takes a path (registered first if new), a video id or a video name. `ingest <path>` registers a file where it lies without copying it, for videos too large to upload through a browser. `worker --once` runs a single job and exits.

Progress (stage and frames done) is written to the job as it runs. A video that cannot be processed ends as `failed` with the reason, and the worker carries on. If the worker is killed mid-job, the next worker to start puts that job back in the queue; a job that has already crashed a worker once is failed instead. Ctrl+C lets the current job finish; a second Ctrl+C interrupts it and requeues it.

### Run the web app

```bash
uv run tracko-anpr web
```

This serves the REST API and the dashboard in one process on `http://localhost:8080` (the API documentation is at `/api/docs`). A worker must be running as well for uploads to be processed; the status endpoint `/api/system/status` says what is and is not ready. The host and port come from `TRACKO_WEB_HOST` and `TRACKO_WEB_PORT` in `.env` (defaults `0.0.0.0` and `8080`, so a browser on Windows reaches the app inside WSL at `localhost:8080`).

Open `http://localhost:8080/upload` to upload an MP4 and process it: the page shows the file's details and, within about half a minute, a **plate-size check** (the worker samples a few frames and says how wide the plates are and whether they are big enough to read; size only), queues the job for the worker, and follows the seven stages live until the annotated video is ready. The status panel at the bottom of the sidebar says whether the database, a worker, the models and the reader are all there. The Overview at `http://localhost:8080/` shows a processed video: the five summary cards (for that video or all videos), the player with the Original / Annotated switch, the processing timeline, the category donut, recognition coverage, the recent detections (click a row to jump the video there and see the evidence) and detections over time. Click any detection to see its evidence and its **Events** (first seen, each reading, number confirmed, corrections, last seen with the travel direction); the same dialog has **Correct this detection**, where a wrong number or vehicle type can be fixed (the system's result is kept beside the correction and the figures do not change; corrections export with Detection History for later evaluation). Video Analysis shows one video large with every tracked vehicle; Detection History searches, filters (including by travel direction: towards or away from the camera), sorts and exports every recognised plate across videos; Demo Registry holds the fictional records (generate them with `uv run tracko-anpr seed-registry`; the page says "Demonstration Data Only"; a record one character away from a confirmed number is shown as a "Possible match" in amber, never as a match; a recognised number can be added to a named list with a description, records can be imported from a CSV, and "Copy link" copies the address of a search); Analytics has the distributions, coverage, activity, timing and confidence; Settings shows the frozen configuration.

### Detect and track vehicles

```bash
uv run tracko-anpr track videos/clear.mp4
```

This runs YOLO26m with the TrackTrack tracker over an MP4 and writes three files to `storage/processed/`:

- `<name>_annotated.mp4` — the video with a box and a label such as `#T14 Motorcycle (0.63)` on every tracked vehicle, at the same resolution, frame rate and frame count as the input, with the original audio (`track` keeps the input size; `process` scales the annotated copy down to 1080p).
- `<name>_detections.csv` — one row per vehicle per frame, with its box in original-frame pixels.
- `<name>_tracks.json` — one summary per track, plus the settings used, timings, speed and memory.

Options: `--max-seconds N` processes only the first N seconds; `--no-video` skips the annotated video; `--output-dir DIR` writes somewhere else.

Only MP4 input is accepted. Resolution and frame rate are read from the video.

### Read number plate crops

The reader lives in its own project, so run it from inside `ocr/`:

```bash
cd ocr
uv run anpr-ocr read ../storage/plate_crops/phase3_smoke/selected
```

It prints the text and confidence for every plate image in the folder. See [ocr/README.md](ocr/README.md).

The main program reaches the reader by starting it as a service. This command, run from the project root, does the whole round trip:

```bash
uv run tracko-anpr read-plates storage/plate_crops/phase3_smoke/selected
```

## Development

Run these from the project root, in WSL:

```bash
uv run ruff check      # lint
uv run ruff format     # format
uv run pytest          # tests
```

`uv run ruff check` covers the whole repository, including `ocr/src`. The OCR project's own tests run in its environment: `cd ocr && uv run pytest`.

Settings come from environment variables, with a `.env` file read first if present. Copy `.env.example` to `.env` to set them; `.env` is git-ignored. The defaults are in `src/tracko_anpr/config.py`.

The model files and the PaddleOCR source code are not in git. Where to get them, and the exact versions used, are recorded in [ocr/README.md](ocr/README.md) and in the "System Setup" section of `ARCHITECTURE.md`.

## Setup

Everything runs inside WSL (Ubuntu 24.04), not Windows PowerShell. The project folder stays on the Windows drive.

### Database

PostgreSQL 18 runs in a Docker container inside WSL, defined in `docker-compose.yml`. Its data lives in a named Docker volume, so it survives the container being removed.

```bash
cd /mnt/c/Users/ontashai/Desktop/tracko-anpr
cp .env.example .env          # then set POSTGRES_PASSWORD to something real
docker compose up -d
docker compose ps             # wait until the container says "healthy"
uv run alembic upgrade head   # create the tables
uv run tracko-anpr db-status  # check the connection and see what is stored
```

`.env` is git-ignored. `docker compose down` stops the container and keeps the data; `docker compose down -v` would delete it.

The tables are described in section 11 of `ARCHITECTURE.md`. After changing `src/tracko_anpr/db/models.py`, run `uv run alembic revision --autogenerate -m "what changed"`, read the file it writes under `migrations/versions/`, then `uv run alembic upgrade head`.

### PyTorch and Ultralytics

`pyproject.toml` points `torch` and `torchvision` at PyTorch's CUDA 12.6 download index, so the plain command below fetches the build that matches the GPU driver.

```bash
cd /mnt/c/Users/ontashai/Desktop/tracko-anpr
export UV_LINK_MODE=copy
uv add "torch==2.14.1" torchvision ultralytics
```

`UV_LINK_MODE=copy` tells uv to copy package files into the virtual environment instead of linking them from its cache, which cannot work across the WSL and Windows drives.

Then check that it worked and the GPU is visible:

```bash
uv run python -c "import torch, torchvision, ultralytics; print(torch.__version__, torchvision.__version__, ultralytics.__version__); print('CUDA available:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

Expected output:

```text
2.14.1+cu126 0.29.1+cu126 8.4.203
CUDA available: True
NVIDIA GeForce RTX 4070 Ti SUPER
```

These packages are already recorded in `pyproject.toml` and `uv.lock`. On a fresh clone, `uv sync` installs the same versions; `uv add` is only needed when adding a new package.

### PaddlePaddle (OCR environment)

The number plate reader runs in its own environment in `ocr/`, separate from the main one, because PaddlePaddle and PyTorch need different versions of the same NVIDIA library. `ocr/pyproject.toml` points `paddlepaddle-gpu` at Paddle's own CUDA 12.6 download index.

```bash
cd /mnt/c/Users/ontashai/Desktop/tracko-anpr/ocr
export UV_LINK_MODE=copy
uv add "paddlepaddle-gpu==3.3.1" safetensors numpy opencv-python pillow pyyaml shapely scikit-image pyclipper rapidfuzz tqdm requests packaging
```

Then check that PaddlePaddle works on the GPU:

```bash
uv run python -c "import paddle; print(paddle.__version__); print('CUDA build:', paddle.device.is_compiled_with_cuda()); paddle.utils.run_check()"
```

You should see `3.3.1`, `CUDA build: True`, and a final line saying PaddlePaddle is installed successfully.

What to expect:

- **A warning about `VIRTUAL_ENV`:** when the terminal has the main `(tracko-anpr)` environment active, uv says it is ignoring it. That is harmless; uv creates a separate `ocr/.venv`, which is the point. Run `deactivate` first to avoid the warning.
- **A `libcuda.so ... cannot open shared object file` message:** it was printed on this machine, but the GPU check still passed. If the OCR model later fails to use the GPU, try `export LD_LIBRARY_PATH=/usr/lib/wsl/lib:$LD_LIBRARY_PATH`.

These packages are recorded in `ocr/pyproject.toml` and `ocr/uv.lock`. On a fresh clone, run `uv sync` inside `ocr/` to install the same versions.

### PaddleOCR source code

The Awiros OCR model is not a pip package: its network is built from PaddleOCR's own source code, so that code must be present on disk. It goes in `ocr/vendor/PaddleOCR`, which is git-ignored, pinned to version `v3.7.0`.

```bash
cd /mnt/c/Users/ontashai/Desktop/tracko-anpr
git clone --depth 1 --branch v3.7.0 https://github.com/PaddlePaddle/PaddleOCR.git ocr/vendor/PaddleOCR
```

The download is about 243 MB. The exact commit, and the model files that go with it, are recorded in [ocr/README.md](ocr/README.md).
