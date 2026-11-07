# tracko-anpr

Proof of concept for Indian vehicle detection, tracking and number plate recognition (ANPR) on uploaded MP4 videos. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design and [PLAN.md](PLAN.md) for the build plan and progress.

## Usage

Run from the project root, in WSL.

### Process a video from start to finish

```bash
uv run tracko-anpr process videos/zoomed-in.mp4
```

This runs the whole pipeline over an MP4: vehicle detection and tracking, plate detection, plate reading, validation across frames, and the annotated video. It prints each stage as it goes, then a summary: tracks, vehicles by type, how many number plates were confirmed, unconfirmed or not detected, recognition coverage (which is not accuracy), and the confirmed numbers.

Results go under `storage/`, in folders named after the video:

- `storage/processed/<name>/annotated.mp4` — the video with every vehicle boxed and labelled, plates outlined in amber, and each number shown as confirmed (`KL10AB1234 (0.97)`) or `unconfirmed`. Same resolution, frame rate and frame count as the input, with the original audio.
- `storage/processed/<name>/results.json` — one record per track (type, when it was seen, plate decision and the reason for it), plus the summary, timings and settings.
- `storage/processed/<name>/detections.csv` — one row per vehicle per frame.
- `storage/processed/<name>/plates.csv` — one row per plate examined, with what the reader made of it.
- `storage/vehicle_crops/<name>/` and `storage/plate_crops/<name>/` — the cut-out images.

The run is also recorded in the database (see "Database" under Setup): a `videos` row for the file, a `processing_jobs` row for this run, and one row per track, plate examined and plate decision. `uv run tracko-anpr db-status` shows what is stored and the overall figures.

Options: `--max-seconds N` processes only the first N seconds; `--no-video` skips the annotated video; `--name NAME` chooses the folder name; `--no-db` writes files only. Processing the same video again replaces its earlier result files and adds a new job to the same video; the dashboard shows the latest.

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

Open `http://localhost:8080/upload` to upload an MP4 and process it: the page shows the file's details, queues the job for the worker, and follows the seven stages live until the annotated video is ready. The status panel at the bottom of the sidebar says whether the database, a worker, the models and the reader are all there. The Overview at `http://localhost:8080/` shows a processed video: the five summary cards (for that video or all videos), the player with the Original / Annotated switch, the processing timeline, the category donut, recognition coverage, the recent detections (click a row to jump the video there and see the evidence) and detections over time. The remaining pages are built in Phase 13.

### Detect and track vehicles

```bash
uv run tracko-anpr track videos/clear.mp4
```

This runs YOLO26m with the TrackTrack tracker over an MP4 and writes three files to `storage/processed/`:

- `<name>_annotated.mp4` — the video with a box and a label such as `#T14 Motorcycle (0.63)` on every tracked vehicle, at the same resolution, frame rate and frame count as the input, with the original audio.
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
