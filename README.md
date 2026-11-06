# tracko-anpr

Proof of concept for Indian vehicle detection, tracking and number plate recognition (ANPR) on uploaded MP4 videos. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

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
