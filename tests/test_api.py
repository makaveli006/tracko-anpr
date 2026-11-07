"""The API and the service layer behind it, on SQLite with a temporary storage folder.

No model runs here: results are stored with the same builders the database tests use, and
processing requests only queue a job. The tiny upload videos are made with FFmpeg.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from result_builders import a_result, video_info
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from tracko_anpr.api.app import create_app
from tracko_anpr.config import load_settings
from tracko_anpr.db.models import COMMAND_LINE, PROCESSING, Base, DemoRegistryEntry
from tracko_anpr.db.session import session_scope
from tracko_anpr.db.store import create_job, register_video, store_result
from tracko_anpr.services.readiness import record_worker_heartbeat

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg is not installed"
)


@pytest.fixture
def settings(tmp_path):
    return load_settings(root=tmp_path, environ={})


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.begin() as connection:  # look migrated, as the real database is
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('test')"))
    return engine


@pytest.fixture
def app(settings, engine):
    return create_app(settings, engine, dashboard=False)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def tiny_mp4(path: Path, seconds: float = 1.0) -> Path:
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=size=64x48:rate=10:duration={seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ]  # fmt: skip
    subprocess.run(command, check=True)
    return path


def stored_run(app, settings, name="clip_part01", with_files=True) -> int:
    """A completed job with the builders' result, and the files it points at under storage/. Returns the video id."""
    info = video_info(name)
    # The builders put files under /project; the API serves files under the test root, so point there.
    info = type(info)(
        settings.root / "videos" / f"{name}.mp4", info.width, info.height, info.fps, info.frame_count, info.duration_s
    )
    result = a_result(info)
    out = settings.processed_dir / name
    result.files = {key: settings.root / Path(*path.parts[2:]) for key, path in result.files.items()}
    if with_files:
        out.mkdir(parents=True, exist_ok=True)
        result.files["annotated_video"].write_bytes(bytes(range(256)) * 4)  # 1,024 bytes of "video"
        result.files["results"].write_text("{}")
        for vehicle in result.vehicles:
            for sighting in vehicle.sightings:
                crop = settings.root / Path(*sighting.crop_file.parts[2:])
                crop.parent.mkdir(parents=True, exist_ok=True)
                crop.write_bytes(b"\x89PNG\r\n\x1a\n")
                sighting.crop_file = crop
            if vehicle.vehicle_crop is not None:
                crop = settings.root / Path(*vehicle.vehicle_crop.parts[2:])
                crop.parent.mkdir(parents=True, exist_ok=True)
                crop.write_bytes(b"\xff\xd8\xff")
                vehicle.vehicle_crop = crop
            if vehicle.plate_crop is not None:
                vehicle.plate_crop = settings.root / Path(*vehicle.plate_crop.parts[2:])
    with session_scope(app.state.session_factory) as session:
        video = register_video(session, info, settings.root, COMMAND_LINE)
        job = create_job(session, video, PROCESSING)
        store_result(session, job, result, settings.root)
        return video.id


# --- system -------------------------------------------------------------------------------------


def test_system_status_tells_the_truth_about_a_missing_worker(client):
    status = client.get("/api/system/status").json()
    checks = {check["name"]: check for check in status["checks"]}
    assert checks["database"]["ok"] is True
    assert checks["worker"]["ok"] is False and "Start one" in checks["worker"]["detail"]
    assert status["ready"] is False
    assert {"gpu", "models", "ocr", "ffmpeg"} <= set(checks)


def test_a_recent_worker_heartbeat_turns_the_worker_check_green(client, app):
    with session_scope(app.state.session_factory) as session:
        record_worker_heartbeat(session, "worker-7")
    checks = {check["name"]: check for check in client.get("/api/system/status").json()["checks"]}
    assert checks["worker"]["ok"] is True and "worker-7" in checks["worker"]["detail"]


def test_summary_is_defined_on_an_empty_system(client):
    summary = client.get("/api/summary").json()
    assert summary["total_vehicles"] == 0 and summary["videos_processed"] == 0
    assert summary["recognition_coverage"] is None


# --- uploads ------------------------------------------------------------------------------------


def test_a_file_that_is_not_an_mp4_is_refused_with_a_clear_message(client):
    response = client.post("/api/videos", files={"file": ("holiday.mov", b"\x00" * 100, "video/quicktime")})
    assert response.status_code == 400
    assert "Only MP4 videos are accepted" in response.json()["detail"]
    assert "holiday.mov" in response.json()["detail"]


def test_an_mp4_that_is_not_really_a_video_is_refused_and_not_kept(client, settings):
    response = client.post("/api/videos", files={"file": ("fake.mp4", b"not a video at all", "video/mp4")})
    assert response.status_code == 400
    assert "could not be read as a video" in response.json()["detail"]
    assert not list(settings.uploads_dir.glob("*.mp4"))
    assert not list((settings.uploads_dir / ".incoming").glob("*"))  # the part file is gone too


def test_an_empty_upload_is_refused(client):
    response = client.post("/api/videos", files={"file": ("empty.mp4", b"", "video/mp4")})
    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


@needs_ffmpeg
def test_a_real_mp4_is_stored_under_uploads_and_registered(client, settings, tmp_path):
    source = tiny_mp4(tmp_path / "source.mp4")
    with source.open("rb") as handle:
        response = client.post("/api/videos", files={"file": ("My Clip.mp4", handle, "video/mp4")})
    assert response.status_code == 201, response.text
    video = response.json()
    assert video["name"] == "My-Clip"
    assert video["original_filename"] == "My Clip.mp4"
    assert (video["width"], video["height"]) == (64, 48)
    assert video["duration_s"] > 0 and video["source"] == "upload"
    assert (settings.uploads_dir / "My-Clip.mp4").is_file()
    assert not (settings.uploads_dir / "My-Clip.part.mp4").exists()
    assert client.get(f"/api/videos/{video['id']}").json()["name"] == "My-Clip"
    assert client.get("/api/videos").json()[0]["id"] == video["id"]


@needs_ffmpeg
def test_uploading_the_same_name_twice_keeps_both(client, settings, tmp_path):
    source = tiny_mp4(tmp_path / "source.mp4")
    names = []
    for _ in range(2):
        with source.open("rb") as handle:
            names.append(client.post("/api/videos", files={"file": ("clip.mp4", handle, "video/mp4")}).json()["name"])
    assert names == ["clip", "clip-2"]
    assert (settings.uploads_dir / "clip-2.mp4").is_file()


@needs_ffmpeg
def test_a_file_on_disk_can_be_registered_without_copying(client, settings, tmp_path):
    (settings.root / "videos").mkdir(exist_ok=True)
    source = tiny_mp4(settings.root / "videos" / "big.mp4")
    response = client.post("/api/videos/ingest", json={"path": str(source)})
    assert response.status_code == 201, response.text
    assert response.json()["source"] == "ingest"
    assert response.json()["name"] == "big"
    assert client.get(f"/api/videos/{response.json()['id']}/original").status_code == 200


def test_ingesting_a_missing_path_is_a_clear_error(client):
    response = client.post("/api/videos/ingest", json={"path": "/nowhere/nothing.mp4"})
    assert response.status_code == 400
    assert "No such file" in response.json()["detail"]


# --- processing ---------------------------------------------------------------------------------


@needs_ffmpeg
def test_processing_queues_a_job_once_and_reports_its_seven_stages(client, tmp_path):
    source = tiny_mp4(tmp_path / "source.mp4")
    with source.open("rb") as handle:
        video_id = client.post("/api/videos", files={"file": ("clip.mp4", handle, "video/mp4")}).json()["id"]
    first = client.post(f"/api/videos/{video_id}/process")
    assert first.status_code == 202
    job = first.json()
    assert job["status"] == "queued" and job["progress"] == 0.0
    assert [stage["name"] for stage in job["stages"]][:2] == ["video_uploaded", "vehicle_detection"]
    assert len(job["stages"]) == 7
    second = client.post(f"/api/videos/{video_id}/process").json()
    assert second["id"] == job["id"]  # the pending job is reused
    assert client.get(f"/api/jobs/{job['id']}").json()["video_id"] == video_id
    assert client.get("/api/jobs").json()[0]["id"] == job["id"]
    listed = client.get(f"/api/videos/{video_id}").json()
    assert listed["latest_job"]["status"] == "queued" and listed["completed_job_id"] is None


def test_processing_an_unknown_video_is_404(client):
    assert client.post("/api/videos/999/process").status_code == 404
    assert client.get("/api/jobs/999").status_code == 404


# --- results ------------------------------------------------------------------------------------


def test_results_detections_and_analytics_for_a_processed_video(client, app, settings):
    video_id = stored_run(app, settings)
    found = client.get(f"/api/videos/{video_id}/results").json()
    assert found["job_id"] is not None
    assert found["summary"]["total_vehicles"] == 4 and found["summary"]["confirmed_plates"] == 2
    assert found["by_class"] == {"Car": 2, "Motorcycle": 1, "Bus": 0, "Truck": 1}
    assert sum(count for _, count in found["detections_over_time"]) == 4
    assert found["annotated_video_path"].endswith("annotated.mp4")

    rows = client.get(f"/api/videos/{video_id}/detections").json()
    assert [row["detection"]["track_id"] for row in rows] == [7, 3, 2, 1]
    assert rows[0]["detection"]["registration_number"] == "KL10CD5678"
    assert rows[0]["registry_match"] is None
    assert client.get(f"/api/videos/{video_id}/detections?limit=2").json().__len__() == 2

    figures = client.get(f"/api/videos/{video_id}/analytics").json()
    assert figures["scope"] == "video" and figures["runs"][0]["processing_seconds"] == 200.0
    assert figures["runs"][0]["detect_track_ms_per_frame"] == round(1000 * 100 / 3600, 2)
    assert sum(count for _, count in figures["confidence_distribution"]) == 2
    assert client.get("/api/analytics").json()["scope"] == "all"
    assert client.get(f"/api/videos/{video_id}").json()["completed_job_id"] == found["job_id"]


def test_one_detection_in_full_with_its_frame_by_frame_evidence(client, app, settings):
    video_id = stored_run(app, settings)
    rows = client.get(f"/api/videos/{video_id}/detections").json()
    track_pk = next(row["detection"]["track_pk"] for row in rows if row["detection"]["track_id"] == 1)
    detail = client.get(f"/api/detections/{track_pk}").json()
    assert detail["detection"]["registration_number"] == "KL07AB1234"
    assert detail["frames_seen"] == 91
    assert len(detail["observations"]) == 1
    assert detail["observations"][0]["text"] == "KL07AB1234"
    assert detail["observations"][0]["crop_path"].startswith("storage/plate_crops/")
    assert client.get("/api/detections/99999").status_code == 404


def test_history_filters_sorts_pages_and_exports(client, app, settings):
    stored_run(app, settings, "one")
    stored_run(app, settings, "two")
    page = client.get("/api/detections").json()
    assert page["total"] == 8 and len(page["rows"]) == 8
    assert client.get("/api/detections?status=confirmed").json()["total"] == 4
    assert client.get("/api/detections?vehicle_type=Truck").json()["total"] == 2
    assert client.get("/api/detections?search=cd56").json()["total"] == 2
    assert client.get("/api/detections?limit=3&offset=6").json()["rows"].__len__() == 2
    by_confidence = client.get("/api/detections?sort=confidence&descending=false").json()["rows"]
    assert by_confidence[0]["detection"]["status"] == "not_detected"
    csv_text = client.get("/api/detections/export.csv?status=confirmed").text
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("video,track,vehicle_type")
    assert len(lines) == 5 and "KL07AB1234" in csv_text


def test_a_confirmed_number_in_the_demo_registry_shows_as_a_match(client, app, settings):
    video_id = stored_run(app, settings)
    with session_scope(app.state.session_factory) as session:
        session.add(
            DemoRegistryEntry(
                registration_number="KL07AB1234",
                owner_name="A. Demo",
                vehicle_description="Maruti Swift",
                vehicle_type="Car",
                colour="White",
                registered_at="Ernakulam RTO",
                valid_until=date(2030, 1, 1),
            )  # fmt: skip
        )
    rows = client.get(f"/api/videos/{video_id}/detections").json()
    matched = next(row for row in rows if row["detection"]["track_id"] == 1)
    assert matched["registry_match"]["owner_name"] == "A. Demo"
    assert matched["registry_match"]["fictional"] is True
    lookup = client.get("/api/registry/KL07AB1234").json()
    assert lookup["match"] is True and "fictional" in lookup["disclaimer"]
    assert client.get("/api/registry/KL00ZZ0000").json()["match"] is False
    assert client.get("/api/registry?search=07ab").json()["entries"][0]["registration_number"] == "KL07AB1234"


# --- files --------------------------------------------------------------------------------------


def test_the_annotated_video_streams_with_range_requests(client, app, settings):
    video_id = stored_run(app, settings)
    whole = client.get(f"/api/videos/{video_id}/annotated")
    assert whole.status_code == 200 and len(whole.content) == 1024
    assert whole.headers["accept-ranges"] == "bytes"
    part = client.get(f"/api/videos/{video_id}/annotated", headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.headers["content-range"] == "bytes 100-199/1024"
    assert part.content == (bytes(range(256)) * 4)[100:200]


def test_downloads_are_attachments_and_missing_files_are_404(client, app, settings):
    video_id = stored_run(app, settings)
    response = client.get(f"/api/videos/{video_id}/download/annotated")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="clip_part01_annotated.mp4"'
    assert client.get(f"/api/videos/{video_id}/download/detections").status_code == 404  # never written
    assert client.get(f"/api/videos/{video_id}/download/nonsense").status_code == 404


def test_a_video_without_results_has_no_annotated_video_yet(client, app, settings):
    video_id = stored_run(app, settings, "bare", with_files=False)
    response = client.get(f"/api/videos/{video_id}/annotated")
    assert response.status_code == 404 and "yet" in response.json()["detail"]


def test_crop_images_are_served_and_nothing_outside_the_crop_folders_is(client, app, settings):
    video_id = stored_run(app, settings)
    rows = client.get(f"/api/videos/{video_id}/detections").json()
    plate = next(row["detection"]["plate_crop_path"] for row in rows if row["detection"]["track_id"] == 1)
    vehicle = next(row["detection"]["vehicle_crop_path"] for row in rows if row["detection"]["track_id"] == 1)
    assert client.get(f"/api/images/{plate}").headers["content-type"] == "image/png"
    assert client.get(f"/api/images/{vehicle}").headers["content-type"] == "image/jpeg"
    (settings.root / "secret.png").write_bytes(b"x")
    assert client.get("/api/images/secret.png").status_code == 404
    assert client.get("/api/images/storage/vehicle_crops/../../secret.png").status_code == 404
    assert client.get("/api/images/storage/processed/clip_part01/results.json").status_code == 404


# --- settings -----------------------------------------------------------------------------------


def test_settings_show_the_frozen_pipeline_values_and_remember_changes(client):
    items = {item["key"]: item for item in client.get("/api/settings").json()}
    assert items["vehicle_image_size"]["value"] == 1536
    assert items["confirm_confidence"]["value"] == 0.85
    assert items["vehicle_image_size"]["applies_to_processing"] is False
    assert "***" in items["database"]["value"] or "@" in items["database"]["value"]
    changed = client.put("/api/settings/vehicle_image_size", json={"value": 1280}).json()
    item = next(i for i in changed if i["key"] == "vehicle_image_size")
    assert item["value"] == 1280 and item["default"] == 1536 and item["updated_at"] is not None
    assert client.put("/api/settings/no_such_setting", json={"value": 1}).status_code == 404


# --- the dashboard mounts on the same app -------------------------------------------------------


def test_the_dashboard_pages_and_theme_are_served_from_the_same_process(settings, engine):
    # NiceGUI can be mounted once per process, so this is the one test that mounts it.
    with TestClient(create_app(settings, engine, dashboard=True)) as client:
        for path in ("/", "/upload", "/analysis", "/history", "/registry", "/analytics", "/settings"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "Vehicle ANPR POC" in response.text
        theme = client.get("/dashboard-static/theme.css")
        assert theme.status_code == 200 and "--accent-green: #36d428" in theme.text
        assert "#5898d4" not in theme.text  # Quasar's default blue never reaches the page
        font = client.get("/dashboard-static/fonts/InterVariable.woff2")
        assert font.status_code == 200 and len(font.content) > 100_000
        assert client.get("/api/system/status").status_code == 200  # the API is still there


def test_the_registry_seeder_makes_matches_and_non_matches_and_is_repeatable(app, settings):
    from tracko_anpr.services import registry, registry_seed

    stored_run(app, settings)
    with session_scope(app.state.session_factory) as session:
        first = registry_seed.seed(session, share=1.0, extra=2)
        assert first.confirmed_numbers == 2  # KL07AB1234 and KL10CD5678
        assert first.created_from_videos == 2 and first.created_extra == 2
        again = registry_seed.seed(session, share=1.0, extra=2)
        assert again.created_from_videos == 0 and again.skipped_existing == 2 and again.created_extra == 0
        assert registry.count(session) == 4
        numbers = registry.recognized_numbers(session)
        assert {n.registration_number: n.match for n in numbers} == {"KL07AB1234": True, "KL10CD5678": True}
        half = registry_seed.seed(session, share=0.0, extra=0, reset=True)
        assert half.created_from_videos == 0 and registry.count(session) == 0
        assert all(not n.match for n in registry.recognized_numbers(session))
        record = registry.lookup(session, "kl07ab1234")
        assert record is None
