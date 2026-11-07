"""A stand-in for the plate reader, used by the client's tests. Not a test file itself.

It speaks the real protocol but reads nothing: the "plate text" is the image's file name.
The first argument picks a behaviour, so the tests can see how the client copes when the
reader misbehaves.

    normal          answer every request
    slow-start      never announce readiness
    fail-start      announce a start-up failure and exit
    die-on-read     exit, without answering, when asked to read
    hang-on-read    stop answering when asked to read
    chatter         print non-protocol lines on standard output as well
    old-protocol    announce an unsupported protocol version
"""

import json
import sys
import time
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else "normal"


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


if mode == "slow-start":
    time.sleep(60)
if mode == "fail-start":
    send({"event": "failed", "error": "FileNotFoundError: OCR model not found"})
    sys.exit(1)

if mode == "chatter":
    print("Skipping import of some module.", flush=True)
send({"event": "ready", "protocol": 99 if mode == "old-protocol" else 1, "device": "fake"})

for line in sys.stdin:
    request = json.loads(line)
    command = request.get("command", "read")
    if command == "ping":
        send({"id": request["id"], "pong": True})
    elif command == "shutdown":
        send({"id": request["id"], "bye": True})
        break
    elif mode == "die-on-read":
        sys.stderr.write("CUDA error: device lost\n")
        sys.stderr.flush()
        sys.exit(3)
    elif mode == "hang-on-read":
        time.sleep(60)
    else:
        if mode == "chatter":
            print("not a protocol line", flush=True)
        if any("explode" in path for path in request["images"]):
            send({"id": request["id"], "error": "RuntimeError: could not read image"})
            continue
        readings = [
            {"text": Path(path).stem.upper(), "confidence": 0.9, "unreadable": False, "ctc_text": ""}
            for path in request["images"]
        ]
        send({"id": request["id"], "readings": readings})
