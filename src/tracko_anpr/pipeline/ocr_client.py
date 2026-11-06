"""Talk to the plate reader, which runs as a separate program in its own environment.

PaddlePaddle (the reader) and PyTorch (everything else) cannot share one Python environment,
so the reader is started as a child process and spoken to in lines of JSON over its standard
input and output. The protocol is described in `ocr/src/anpr_ocr/service.py`.

The client never waits forever: starting and every request have a time limit, and a reader
that has died is reported as an error, with the last lines it wrote, rather than as a hang.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import subprocess
import tempfile
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_START_TIMEOUT = 180.0
DEFAULT_REQUEST_TIMEOUT = 60.0
DEFAULT_BATCH_SIZE = 64
SUPPORTED_PROTOCOL = 1
WSL_DRIVER_LIBRARIES = "/usr/lib/wsl/lib"

_ENDED = object()  # marks the end of the reader's output in the message queue


class OcrError(Exception):
    """The plate reader could not be started, stopped answering, or reported a problem."""


@dataclass(frozen=True)
class PlateReading:
    """What the reader made of one plate crop."""

    text: str
    """Plate text, upper case; empty when nothing could be read."""
    confidence: float
    """How sure the model is, 0 to 1. Not a measure of whether the reading is right."""
    unreadable: bool = False
    """True when the model itself answered that the plate cannot be read."""
    ctc_text: str = ""
    """The model's second decoder's reading: a second opinion, weaker on two-line plates."""


def default_command(ocr_project: Path) -> list[str]:
    """The reader's own executable inside its environment."""
    executable = ocr_project / ".venv" / "bin" / "anpr-ocr"
    if not executable.is_file():
        raise OcrError(
            f"The plate reader is not installed at {executable}. Run `uv sync` inside {ocr_project} "
            "(see 'PaddlePaddle' in README.md)."
        )
    return [str(executable), "serve"]


class OcrClient:
    """Starts the plate reader and sends it plate crops to read.

    Use as a context manager, or call `start()` and `stop()`. If the reader has died,
    the next `read()` starts a fresh one; a death in the middle of a request is raised
    as `OcrError`.
    """

    def __init__(
        self,
        command: Sequence[str],
        cwd: str | Path | None = None,
        start_timeout: float = DEFAULT_START_TIMEOUT,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.command = list(command)
        self.cwd = str(cwd) if cwd is not None else None
        self.start_timeout = start_timeout
        self.request_timeout = request_timeout
        self.batch_size = batch_size
        self.device = ""
        self.starts = 0
        self._process: subprocess.Popen | None = None
        self._messages: queue.Queue = queue.Queue()
        self._log = None
        self._next_id = 0

    @classmethod
    def for_project(cls, ocr_project: str | Path, **options) -> OcrClient:
        """A client for the reader installed in the repository's `ocr/` folder."""
        ocr_project = Path(ocr_project)
        return cls(default_command(ocr_project), cwd=ocr_project, **options)

    # --- life cycle --------------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Start the reader and wait until it says it is ready. Does nothing if it is already running."""
        if self.is_running:
            return
        self._discard_process()

        environment = dict(os.environ)
        environment.pop("VIRTUAL_ENV", None)  # the reader has an environment of its own
        environment["PYTHONUNBUFFERED"] = "1"
        # Under WSL the NVIDIA driver library sits in a folder PaddlePaddle does not search by itself,
        # and it prints a long "libcuda.so" warning on every start. Naming the folder stops that.
        if os.path.isdir(WSL_DRIVER_LIBRARIES):
            existing = environment.get("LD_LIBRARY_PATH", "")
            environment["LD_LIBRARY_PATH"] = WSL_DRIVER_LIBRARIES + (f":{existing}" if existing else "")
        # The reader's own messages go to a file: an unread pipe could fill up and stall it.
        self._log = tempfile.NamedTemporaryFile("w+", prefix="anpr_ocr_", suffix=".log", delete=False)  # noqa: SIM115
        self._messages = queue.Queue()
        try:
            self._process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._log,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as error:
            raise OcrError(f"Could not start the plate reader ({self.command[0]}): {error}") from error
        self.starts += 1
        threading.Thread(target=self._pump, args=(self._process, self._messages), daemon=True).start()

        message = self._next_message(self.start_timeout, "start up")
        if message.get("event") == "failed":
            self._kill()
            raise OcrError(f"The plate reader failed to start: {message.get('error', 'no reason given')}")
        if message.get("event") != "ready":
            self._kill()
            raise OcrError(f"The plate reader sent an unexpected first message: {message}")
        if message.get("protocol") != SUPPORTED_PROTOCOL:
            self._kill()
            raise OcrError(
                f"The plate reader speaks protocol {message.get('protocol')}, expected {SUPPORTED_PROTOCOL}."
            )
        self.device = str(message.get("device", ""))

    def stop(self) -> None:
        """Ask the reader to finish; force it if it does not."""
        if self.is_running:
            try:
                self._send({"id": self._new_id(), "command": "shutdown"})
                self._process.wait(timeout=10)
            except (OcrError, subprocess.TimeoutExpired):
                pass
        self._kill()

    def restart(self) -> None:
        self._kill()
        self.start()

    def __enter__(self) -> OcrClient:
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.stop()

    # --- requests ----------------------------------------------------------------------------

    def read(self, images: Sequence[str | Path]) -> list[PlateReading]:
        """Read plate crops given as image file paths; one reading per path, in order."""
        paths = [str(Path(image).resolve()) for image in images]
        if not paths:
            return []
        if not self.is_running:
            self.start()

        readings: list[PlateReading] = []
        for start in range(0, len(paths), self.batch_size):
            batch = paths[start : start + self.batch_size]
            reply = self._request({"images": batch})
            answers = reply.get("readings")
            if not isinstance(answers, list) or len(answers) != len(batch):
                raise OcrError(f"The plate reader answered {len(batch)} images with: {reply}")
            readings += [
                PlateReading(
                    text=str(answer.get("text", "")),
                    confidence=float(answer.get("confidence", 0.0)),
                    unreadable=bool(answer.get("unreadable", False)),
                    ctc_text=str(answer.get("ctc_text", "")),
                )
                for answer in answers
            ]
        return readings

    def ping(self) -> bool:
        """True when the reader answers. Starts it if needed."""
        if not self.is_running:
            self.start()
        return bool(self._request({"command": "ping"}).get("pong"))

    # --- internals ---------------------------------------------------------------------------

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _request(self, body: dict) -> dict:
        request_id = self._new_id()
        self._send({"id": request_id, **body})
        while True:
            reply = self._next_message(self.request_timeout, "answer")
            if reply.get("id") != request_id:
                continue  # a leftover from an earlier, abandoned request
            if "error" in reply:
                raise OcrError(f"The plate reader reported: {reply['error']}")
            return reply

    def _send(self, message: dict) -> None:
        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as error:
            exit_note, last_words = self._exit_note(), self._log_note()
            self._kill()
            raise OcrError(f"The plate reader has stopped{exit_note}.{last_words}") from error

    def _next_message(self, timeout: float, doing: str) -> dict:
        """The reader's next JSON message, or an OcrError if it dies or takes too long."""
        try:
            item = self._messages.get(timeout=timeout)
        except queue.Empty:
            # Read the reader's last words before stopping it: stopping also discards its log.
            last_words = self._log_note()
            self._kill()
            raise OcrError(
                f"The plate reader did not {doing} within {timeout:g} seconds and was stopped.{last_words}"
            ) from None
        if item is _ENDED:
            exit_note, last_words = self._exit_note(), self._log_note()
            self._kill()
            raise OcrError(f"The plate reader stopped before it could {doing}{exit_note}.{last_words}")
        return item

    @staticmethod
    def _pump(process: subprocess.Popen, messages: queue.Queue) -> None:
        """Runs in a thread: turn the reader's output lines into messages, then mark the end."""
        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue  # not a protocol message; the reader's own chatter belongs on its error stream
                if isinstance(message, dict):
                    messages.put(message)
        except (OSError, ValueError):
            pass
        messages.put(_ENDED)

    def _exit_note(self) -> str:
        if self._process is None:
            return ""
        try:
            code = self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return ""
        return f" (exit code {code})"

    def _log_note(self, lines: int = 6) -> str:
        """The last few lines the reader wrote, to explain a failure."""
        if self._log is None:
            return ""
        try:
            self._log.flush()
            text = Path(self._log.name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        tail = [line for line in text.splitlines() if line.strip()][-lines:]
        return " Its last messages: " + " | ".join(tail) if tail else ""

    def _kill(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._process.wait(timeout=10)
        self._discard_process()

    def _discard_process(self) -> None:
        if self._process is not None:
            for stream in (self._process.stdin, self._process.stdout):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
        self._process = None
        if self._log is not None:
            name = self._log.name
            self._log.close()
            Path(name).unlink(missing_ok=True)
            self._log = None
