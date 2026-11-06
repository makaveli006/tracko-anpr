"""The plate reader as a long-running service, spoken to over standard input and output.

The main application runs in a different Python environment (PyTorch) and cannot import
this one (PaddlePaddle), so it starts this program and exchanges one line of JSON per message:

    service -> {"event": "ready", "protocol": 1, "device": "gpu:0"}     once, after the model has loaded
    client  -> {"id": 7, "images": ["/path/a.png", "/path/b.png"]}
    service -> {"id": 7, "readings": [{"text": "KL07CN9092", "confidence": 0.92,
                                       "unreadable": false, "ctc_text": "KL07CN9092"}, ...]}
    client  -> {"id": 8, "command": "ping"}        service -> {"id": 8, "pong": true}
    client  -> {"id": 9, "command": "shutdown"}    service -> {"id": 9, "bye": true}, then exits

Images are passed as file paths; the crops are on disk anyway. A problem with one request is
answered with {"id": ..., "error": "..."} and the service carries on. Closing standard input
also stops it.

Standard output carries nothing but these messages. Everything else, including whatever
PaddlePaddle prints, is sent to standard error.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from typing import TextIO

PROTOCOL_VERSION = 1

ReadImages = Callable[[list[str]], list]
"""Takes image paths, returns one Reading per path."""


def reading_to_dict(reading) -> dict:
    return {
        "text": reading.text,
        "confidence": round(float(reading.confidence), 4),
        "unreadable": bool(reading.unreadable),
        "ctc_text": reading.ctc_text,
    }


def handle_request(request: object, read_images: ReadImages) -> tuple[dict, bool]:
    """Answer one request. Returns the reply and whether the service should keep running."""
    if not isinstance(request, dict):
        return {"id": None, "error": "a request must be a JSON object"}, True
    request_id = request.get("id")
    command = request.get("command", "read")

    if command == "ping":
        return {"id": request_id, "pong": True}, True
    if command == "shutdown":
        return {"id": request_id, "bye": True}, False
    if command != "read":
        return {"id": request_id, "error": f"unknown command {command!r}"}, True

    images = request.get("images")
    if not isinstance(images, list) or not all(isinstance(path, str) for path in images):
        return {"id": request_id, "error": "'images' must be a list of file paths"}, True
    readings = read_images(images)
    return {"id": request_id, "readings": [reading_to_dict(reading) for reading in readings]}, True


def serve(requests: TextIO, replies: TextIO, read_images: ReadImages, device: str = "") -> int:
    """Announce readiness, then answer requests line by line until told to stop or input ends."""

    def send(message: dict) -> None:
        replies.write(json.dumps(message) + "\n")
        replies.flush()

    send({"event": "ready", "protocol": PROTOCOL_VERSION, "device": device})
    for line in requests:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            send({"id": None, "error": "request was not valid JSON"})
            continue
        try:
            reply, keep_running = handle_request(request, read_images)
        except Exception as error:  # one bad request must not bring the service down
            request_id = request.get("id") if isinstance(request, dict) else None
            reply, keep_running = {"id": request_id, "error": f"{type(error).__name__}: {error}"}, True
        send(reply)
        if not keep_running:
            break
    return 0


def reserve_standard_output() -> TextIO:
    """Keep the real standard output for protocol messages and point everything else at standard error.

    PaddlePaddle and its libraries write to standard output at the operating-system level, not only
    through Python, so the redirection is done on the file descriptor itself.
    """
    protocol_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(protocol_fd, "w", encoding="utf-8", buffering=1)


def run() -> int:
    """Entry point for `anpr-ocr serve`."""
    replies = reserve_standard_output()
    try:
        import cv2

        from anpr_ocr.recognizer import PlateRecognizer

        recognizer = PlateRecognizer()
    except Exception as error:
        # Tell the client why start-up failed instead of leaving it to guess from a closed pipe.
        replies.write(json.dumps({"event": "failed", "error": f"{type(error).__name__}: {error}"}) + "\n")
        replies.flush()
        return 1

    def read_images(paths: list[str]) -> list:
        return recognizer.read([cv2.imread(path) for path in paths])

    return serve(sys.stdin, replies, read_images, device=recognizer.device)
