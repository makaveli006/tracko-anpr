"""The REST API (ARCHITECTURE.md section 3). Thin: every route calls a service and returns what it gets.

The eight endpoints the architecture names, plus what the dashboard needs beyond them: the
system status, the summary cards across all videos, the original video, downloads, crop
images, the cross-video history with export, one detection in full, the registry and the
settings. Videos stream with HTTP range support so the player can seek.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from tracko_anpr.api.app import EngineDep, SessionDep, SettingsDep
from tracko_anpr.config import Settings
from tracko_anpr.db import metrics
from tracko_anpr.db.models import Video
from tracko_anpr.services import (
    analytics,
    app_settings,
    corrections,
    files,
    jobs,
    readiness,
    registry,
    results,
    videos,
)

router = APIRouter(prefix="/api")

DOWNLOAD_KINDS = {
    "annotated": ("annotated_video_path", "annotated.mp4", "video/mp4"),
    "results": ("results_path", "results.json", "application/json"),
    "detections": ("detections_path", "detections.csv", "text/csv"),
    "plates": ("plates_path", "plates.csv", "text/csv"),
}


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=what)


# --- system -------------------------------------------------------------------------------------


@router.get("/system/status", response_model=readiness.SystemStatus)
def system_status(
    settings: Annotated[Settings, SettingsDep],
    engine: Annotated[Engine, EngineDep],
    session: Annotated[Session, SessionDep],
):
    return readiness.system_status(settings, engine, session)


@router.get("/summary", response_model=metrics.Summary)
def summary(session: Annotated[Session, SessionDep], video_id: int | None = None):
    """The five Overview cards: for one video, or across all processed videos."""
    return metrics.summary(session, video_id)


# --- videos -------------------------------------------------------------------------------------


@router.get("/videos", response_model=list[videos.VideoSummary])
def list_videos(session: Annotated[Session, SessionDep]):
    return videos.list_videos(session)


@router.post("/videos", response_model=videos.VideoSummary, status_code=201)
def upload_video(
    session: Annotated[Session, SessionDep],
    settings: Annotated[Settings, SettingsDep],
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
):
    """Upload an MP4. Anything else is refused with a message saying why."""
    chunks = iter(lambda: file.file.read(1 << 20), b"")
    try:
        return videos.save_upload(session, settings, file.filename or "upload.mp4", chunks, name=name)
    except videos.InvalidVideo as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/videos/ingest", response_model=videos.VideoSummary, status_code=201)
def ingest_video(
    session: Annotated[Session, SessionDep],
    settings: Annotated[Settings, SettingsDep],
    path: Annotated[str, Body(embed=True)],
    name: Annotated[str | None, Body(embed=True)] = None,
):
    """Register a video already on this machine's disk, without copying it (for files too large to upload)."""
    if not Path(path).is_file():
        raise HTTPException(status_code=400, detail=f"No such file on the server: {path}")
    try:
        return videos.ingest_file(session, settings, path, name=name)
    except videos.InvalidVideo as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/videos/{video_id}", response_model=videos.VideoSummary)
def get_video(video_id: int, session: Annotated[Session, SessionDep]):
    video = videos.get_video(session, video_id)
    if video is None:
        raise _not_found(f"No video with id {video_id}.")
    return video


@router.post("/videos/{video_id}/process", response_model=jobs.JobStatus, status_code=202)
def process_video(video_id: int, session: Annotated[Session, SessionDep]):
    """Queue the video for the worker. Returns the job (an existing pending job is reused)."""
    try:
        job, _ = jobs.start_processing(session, video_id)
    except jobs.VideoNotFound as error:
        raise _not_found(str(error)) from error
    return job


@router.get("/videos/{video_id}/results", response_model=results.VideoResults)
def video_results(video_id: int, session: Annotated[Session, SessionDep]):
    found = results.video_results(session, video_id)
    if found is None:
        raise _not_found(f"No video with id {video_id}.")
    return found


@router.get("/videos/{video_id}/detections", response_model=list[results.DetectionRow])
def video_detections(video_id: int, session: Annotated[Session, SessionDep], limit: int | None = Query(None, ge=1)):
    if videos.get_video(session, video_id) is None:
        raise _not_found(f"No video with id {video_id}.")
    return results.video_detections(session, video_id, limit=limit)


@router.get("/videos/{video_id}/analytics", response_model=analytics.Analytics)
def video_analytics(video_id: int, session: Annotated[Session, SessionDep]):
    if videos.get_video(session, video_id) is None:
        raise _not_found(f"No video with id {video_id}.")
    return analytics.analytics(session, video_id)


@router.get("/analytics", response_model=analytics.Analytics)
def all_analytics(session: Annotated[Session, SessionDep]):
    return analytics.analytics(session)


def _video_file_response(path: Path, media_type: str, filename: str | None = None) -> FileResponse:
    # FileResponse answers Range requests with 206 Partial Content, which is what lets the player seek.
    headers = {"Accept-Ranges": "bytes"}
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return FileResponse(path, media_type=media_type, headers=headers)


@router.get("/videos/{video_id}/annotated")
def annotated_video(video_id: int, session: Annotated[Session, SessionDep], settings: Annotated[Settings, SettingsDep]):
    found = results.video_results(session, video_id)
    if found is None:
        raise _not_found(f"No video with id {video_id}.")
    try:
        path = files.storage_file(settings, found.annotated_video_path)
    except files.FileNotAvailable as error:
        raise _not_found(f"No annotated video for video {video_id} yet: {error}") from error
    return _video_file_response(path, "video/mp4")


@router.get("/videos/{video_id}/original")
def original_video(video_id: int, session: Annotated[Session, SessionDep], settings: Annotated[Settings, SettingsDep]):
    video = session.get(Video, video_id)
    if video is None:
        raise _not_found(f"No video with id {video_id}.")
    try:
        path = files.video_file(settings, video.file_path)
    except files.FileNotAvailable as error:
        raise _not_found(str(error)) from error
    return _video_file_response(path, "video/mp4")


@router.get("/videos/{video_id}/download/{kind}")
def download(
    video_id: int, kind: str, session: Annotated[Session, SessionDep], settings: Annotated[Settings, SettingsDep]
):
    """Download a result file as an attachment: annotated, results, detections or plates."""
    if kind not in DOWNLOAD_KINDS:
        raise _not_found(f"Unknown download '{kind}'; one of {', '.join(DOWNLOAD_KINDS)}.")
    found = results.video_results(session, video_id)
    if found is None:
        raise _not_found(f"No video with id {video_id}.")
    attribute, filename, media_type = DOWNLOAD_KINDS[kind]
    try:
        path = files.storage_file(settings, getattr(found, attribute))
    except files.FileNotAvailable as error:
        raise _not_found(f"No {kind} file for video {video_id} yet: {error}") from error
    return _video_file_response(path, media_type, filename=f"{found.video_name}_{filename}")


# --- jobs ---------------------------------------------------------------------------------------


@router.get("/jobs", response_model=list[jobs.JobStatus])
def list_jobs(session: Annotated[Session, SessionDep], limit: int = Query(50, ge=1, le=500)):
    return jobs.list_jobs(session, limit)


@router.get("/jobs/{job_id}", response_model=jobs.JobStatus)
def get_job(job_id: int, session: Annotated[Session, SessionDep]):
    job = jobs.get_job(session, job_id)
    if job is None:
        raise _not_found(f"No job with id {job_id}.")
    return job


# --- detections across videos -------------------------------------------------------------------


@router.get("/detections", response_model=results.HistoryPage)
def detection_history(
    session: Annotated[Session, SessionDep],
    video_id: int | None = None,
    status: str | None = None,
    vehicle_type: str | None = None,
    search: str | None = None,
    sort: str = "time",
    descending: bool = True,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    approach: str | None = Query(None, pattern="^(towards|away|none)$"),
):
    return results.detection_history(
        session, video_id, status, vehicle_type, search, sort, descending, offset, limit, approach
    )


@router.get("/detections/export.csv")
def export_detections(
    session: Annotated[Session, SessionDep],
    video_id: int | None = None,
    status: str | None = None,
    vehicle_type: str | None = None,
    search: str | None = None,
    approach: str | None = Query(None, pattern="^(towards|away|none)$"),
):
    text = results.export_history_csv(
        session, video_id=video_id, status=status, vehicle_type=vehicle_type, search=search, approach=approach
    )
    headers = {"Content-Disposition": 'attachment; filename="detections.csv"'}
    return PlainTextResponse(text, media_type="text/csv", headers=headers)


@router.get("/detections/{track_pk}", response_model=results.DetectionDetail)
def detection_detail(track_pk: int, session: Annotated[Session, SessionDep]):
    found = results.detection_detail(session, track_pk)
    if found is None:
        raise _not_found(f"No detection with id {track_pk}.")
    return found


@router.put("/detections/{track_pk}/correction", response_model=results.DetectionDetail)
def correct_detection(
    track_pk: int,
    session: Annotated[Session, SessionDep],
    number: Annotated[str | None, Body(embed=True)] = None,
    vehicle_type: Annotated[str | None, Body(embed=True)] = None,
    corrected_by: Annotated[str, Body(embed=True)] = "",
    note: Annotated[str, Body(embed=True)] = "",
):
    """Record an operator's correction of the number and/or type. The system's result is kept beside it."""
    try:
        corrections.save_correction(session, track_pk, number, vehicle_type, corrected_by, note)
    except corrections.CorrectionError as error:
        if "not in the database" in str(error):
            raise _not_found(str(error)) from error
        raise HTTPException(status_code=400, detail=str(error)) from error
    return results.detection_detail(session, track_pk)


@router.delete("/detections/{track_pk}/correction", response_model=results.DetectionDetail)
def undo_correction(track_pk: int, session: Annotated[Session, SessionDep]):
    """Remove the newest correction of a detection."""
    if results.detection_detail(session, track_pk) is None:
        raise _not_found(f"No detection with id {track_pk}.")
    if not corrections.undo_latest(session, track_pk):
        raise HTTPException(status_code=400, detail="This detection has no correction to undo.")
    return results.detection_detail(session, track_pk)


@router.get("/corrections")
def list_corrections(session: Annotated[Session, SessionDep], video_id: int | None = None):
    """Operators' current corrections over the latest runs, with the summary. The other figures ignore them."""
    return {
        "summary": corrections.summary(session, video_id),
        "corrections": corrections.list_corrections(session, video_id),
    }


@router.get("/images/{relative_path:path}")
def image(relative_path: str, settings: Annotated[Settings, SettingsDep]):
    """A vehicle or plate crop, by the path stored with the detection (under storage/)."""
    try:
        path = files.image_file(settings, relative_path)
    except files.FileNotAvailable as error:
        raise _not_found(str(error)) from error
    return FileResponse(path, media_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg")


# --- demo registry and settings -----------------------------------------------------------------


@router.get("/registry")
def list_registry(session: Annotated[Session, SessionDep], search: str | None = None):
    return {"disclaimer": registry.DISCLAIMER, "entries": registry.list_entries(session, search)}


@router.get("/registry/{registration_number}")
def registry_lookup(registration_number: str, session: Annotated[Session, SessionDep]):
    record = registry.lookup(session, registration_number)
    return {"disclaimer": registry.DISCLAIMER, "match": record is not None, "record": record}


@router.get("/settings", response_model=list[app_settings.SettingItem])
def get_settings(session: Annotated[Session, SessionDep], settings: Annotated[Settings, SettingsDep]):
    return app_settings.current(session, settings)


@router.put("/settings/{key}", response_model=list[app_settings.SettingItem])
def put_setting(
    key: str,
    session: Annotated[Session, SessionDep],
    settings: Annotated[Settings, SettingsDep],
    value: Annotated[object, Body(embed=True)],
):
    known = {item.key for item in app_settings.defaults(settings)}
    if key not in known:
        raise _not_found(f"No setting '{key}'.")
    app_settings.update(session, key, value)
    return app_settings.current(session, settings)
