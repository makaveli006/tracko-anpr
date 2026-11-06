"""The client is tested against a stand-in reader, so no model or GPU is needed."""

import sys
import time
from pathlib import Path

import pytest

from tracko_anpr.pipeline.ocr_client import OcrClient, OcrError, PlateReading, default_command

FAKE = str(Path(__file__).with_name("fake_ocr_service.py"))


def client(mode: str = "normal", **options) -> OcrClient:
    options.setdefault("start_timeout", 20)
    options.setdefault("request_timeout", 20)
    return OcrClient([sys.executable, FAKE, mode], **options)


def test_round_trip_gives_one_reading_per_image_in_order():
    with client() as reader:
        assert reader.device == "fake"
        readings = reader.read(["/crops/kl07cn9092.png", "/crops/kl57b1883.png"])
    assert readings == [PlateReading("KL07CN9092", 0.9), PlateReading("KL57B1883", 0.9)]


def test_reading_nothing_does_not_even_start_the_reader():
    reader = client()
    assert reader.read([]) == []
    assert reader.starts == 0


def test_large_requests_are_split_into_batches_and_stay_in_order():
    with client(batch_size=4) as reader:
        readings = reader.read([f"/crops/p{number:02d}.png" for number in range(10)])
    assert [reading.text for reading in readings] == [f"P{number:02d}" for number in range(10)]


def test_read_starts_the_reader_by_itself_and_ping_works():
    reader = client()
    try:
        assert reader.read(["/crops/a.png"])[0].text == "A"
        assert reader.is_running
        assert reader.ping()
    finally:
        reader.stop()
    assert not reader.is_running


def test_non_protocol_output_from_the_reader_is_ignored():
    with client("chatter") as reader:
        assert reader.read(["/crops/a.png"])[0].text == "A"


def test_a_reader_that_fails_to_start_gives_its_reason():
    with pytest.raises(OcrError, match="failed to start: FileNotFoundError: OCR model not found"):
        client("fail-start").start()


def test_a_reader_that_never_becomes_ready_times_out_instead_of_hanging():
    reader = client("slow-start", start_timeout=1)
    began = time.perf_counter()
    with pytest.raises(OcrError, match="did not start up within 1 seconds"):
        reader.start()
    assert time.perf_counter() - began < 10
    assert not reader.is_running


def test_an_unsupported_protocol_is_refused():
    with pytest.raises(OcrError, match="speaks protocol 99"):
        client("old-protocol").start()


def test_a_missing_executable_is_a_clear_error(tmp_path: Path):
    with pytest.raises(OcrError, match="Could not start the plate reader"):
        OcrClient([str(tmp_path / "no-such-program")]).start()
    with pytest.raises(OcrError, match="not installed"):
        default_command(tmp_path)


def test_a_reader_that_dies_mid_request_is_an_error_with_its_last_words_not_a_hang():
    reader = client("die-on-read")
    reader.start()
    began = time.perf_counter()
    with pytest.raises(OcrError) as failure:
        reader.read(["/crops/a.png"])
    assert time.perf_counter() - began < 10
    message = str(failure.value)
    assert "stopped before it could answer" in message
    assert "exit code 3" in message
    assert "CUDA error: device lost" in message
    assert not reader.is_running


def test_a_reader_that_stops_answering_times_out_and_is_stopped():
    reader = client("hang-on-read", request_timeout=1)
    reader.start()
    with pytest.raises(OcrError, match="did not answer within 1 seconds"):
        reader.read(["/crops/a.png"])
    assert not reader.is_running


def test_after_a_death_the_next_read_starts_a_fresh_reader():
    reader = client("normal")
    try:
        assert reader.read(["/crops/a.png"])[0].text == "A"
        reader._process.kill()  # the reader dies between requests
        reader._process.wait()
        assert reader.read(["/crops/b.png"])[0].text == "B"
        assert reader.starts == 2
    finally:
        reader.stop()


def test_an_error_for_one_request_leaves_the_reader_usable():
    with client() as reader:
        with pytest.raises(OcrError, match="reported: RuntimeError: could not read image"):
            reader.read(["/crops/explode.png"])
        assert reader.read(["/crops/a.png"])[0].text == "A"
        assert reader.starts == 1


def test_restart_gives_a_working_reader():
    with client() as reader:
        reader.restart()
        assert reader.starts == 2
        assert reader.read(["/crops/a.png"])[0].text == "A"
