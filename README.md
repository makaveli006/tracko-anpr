# tracko-anpr

Proof of concept for Indian vehicle detection, tracking and number plate recognition (ANPR) on uploaded MP4 videos. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design and [PLAN.md](PLAN.md) for the build plan and progress.

## Usage

Run from the project root, in WSL.

### Detect and track vehicles

```bash
uv run tracko-anpr track videos/clips/trafiic/trafiic_part01.mp4
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
