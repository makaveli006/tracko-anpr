"""Tests for the service's message handling, with a stand-in for the model."""

import io
import json
from dataclasses import dataclass

from anpr_ocr.service import PROTOCOL_VERSION, handle_request, serve


@dataclass
class FakeReading:
    text: str
    confidence: float = 0.9
    unreadable: bool = False
    ctc_text: str = ""


def read_names(paths: list[str]) -> list[FakeReading]:
    """Pretends to read each image: the 'plate text' is just the file name."""
    return [FakeReading(path.rsplit("/", 1)[-1].upper(), ctc_text="X") for path in paths]


def run_service(*lines: str, reader=read_names) -> list[dict]:
    replies = io.StringIO()
    code = serve(io.StringIO("".join(line + "\n" for line in lines)), replies, reader, device="test")
    assert code == 0
    return [json.loads(line) for line in replies.getvalue().splitlines()]


def test_readiness_is_announced_first_with_protocol_and_device():
    assert run_service() == [{"event": "ready", "protocol": PROTOCOL_VERSION, "device": "test"}]


def test_a_read_request_gets_one_reading_per_image_in_order():
    _, reply = run_service(json.dumps({"id": 7, "images": ["/crops/a.png", "/crops/b.png"]}))
    assert reply["id"] == 7
    assert [reading["text"] for reading in reply["readings"]] == ["A.PNG", "B.PNG"]
    assert reply["readings"][0] == {"text": "A.PNG", "confidence": 0.9, "unreadable": False, "ctc_text": "X"}


def test_an_empty_request_is_answered_with_no_readings():
    _, reply = run_service(json.dumps({"id": 1, "images": []}))
    assert reply == {"id": 1, "readings": []}


def test_ping_and_shutdown():
    replies = run_service(
        json.dumps({"id": 1, "command": "ping"}),
        json.dumps({"id": 2, "command": "shutdown"}),
        json.dumps({"id": 3, "command": "ping"}),  # never reached
    )
    assert replies[1:] == [{"id": 1, "pong": True}, {"id": 2, "bye": True}]


def test_bad_requests_get_an_error_and_the_service_carries_on():
    replies = run_service(
        "this is not json",
        json.dumps([1, 2, 3]),
        json.dumps({"id": 4, "command": "dance"}),
        json.dumps({"id": 5, "images": "not-a-list"}),
        json.dumps({"id": 6, "images": [1, 2]}),
        "",
        json.dumps({"id": 7, "command": "ping"}),
    )[1:]
    assert [reply.get("id") for reply in replies] == [None, None, 4, 5, 6, 7]
    assert all("error" in reply for reply in replies[:5])
    assert replies[5] == {"id": 7, "pong": True}


def test_a_failure_while_reading_is_reported_for_that_request_only():
    def broken(paths):
        if "bad" in paths[0]:
            raise RuntimeError("GPU fell over")
        return read_names(paths)

    replies = run_service(
        json.dumps({"id": 1, "images": ["/crops/bad.png"]}),
        json.dumps({"id": 2, "images": ["/crops/good.png"]}),
        reader=broken,
    )[1:]
    assert replies[0] == {"id": 1, "error": "RuntimeError: GPU fell over"}
    assert replies[1]["readings"][0]["text"] == "GOOD.PNG"


def test_handle_request_says_whether_to_keep_running():
    assert handle_request({"id": 1, "command": "ping"}, read_names)[1] is True
    assert handle_request({"id": 1, "command": "shutdown"}, read_names)[1] is False
