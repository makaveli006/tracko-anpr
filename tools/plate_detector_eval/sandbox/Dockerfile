# Sandbox for loading third-party plate-detector weights.
#
# The image is built with network access (to install packages) and then RUN WITHOUT ANY:
#   docker run --network none --read-only --cap-drop ALL ...
# See ../README.md for the exact command. A `.pt` file can run code when loaded; inside this
# container that code has no network, no credentials, no project files and nothing to write to
# except the results folder.

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch: the sandbox does not get the GPU.
RUN pip install --no-cache-dir torch==2.14.1 torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir ultralytics==8.4.203 onnx onnxruntime safetensors

RUN useradd --create-home --uid 1000 runner
USER runner
WORKDIR /work

# Ultralytics must not try to install or download anything, and may only write under /tmp.
ENV YOLO_AUTOINSTALL=False \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    MPLCONFIGDIR=/tmp/matplotlib \
    HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1
