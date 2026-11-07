"""Everything the Overview page shows, assembled in one call (DESIGN sections 6 to 13).

The video selector chooses which processed video the player, timeline, charts and
detections table show; the scope switch lets the five cards show that video or all videos.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from tracko_anpr.db import metrics
from tracko_anpr.db.metrics import Summary
from tracko_anpr.services import jobs, results, videos
from tracko_anpr.services.jobs import JobStatus
from tracko_anpr.services.results import DetectionRow, VideoResults
from tracko_anpr.services.videos import VideoSummary

RECENT_LIMIT = 8


@dataclass(frozen=True)
class Overview:
    processed_videos: list[VideoSummary]
    """Videos with a completed job, newest first: the selector's choices."""
    selected: VideoSummary | None
    cards: Summary
    """The five cards, for the selected video or for all videos according to `scope`."""
    scope: str
    """'video' or 'all'."""
    overall: Summary
    """Across all videos, for the header's "Processed: N videos | Last run"."""
    results: VideoResults | None
    job: JobStatus | None
    recent: list[DetectionRow]


def overview(session: Session, video_id: int | None = None, scope: str = "video") -> Overview:
    """The page's data. With no `video_id`, the most recently processed video is selected."""
    processed = [video for video in videos.list_videos(session) if video.completed_job_id is not None]
    selected = next((video for video in processed if video.id == video_id), None)
    if selected is None and video_id is None and processed:
        selected = processed[0]
    overall = metrics.summary(session)
    if selected is None:
        return Overview(processed, None, overall, "all", overall, None, None, [])
    found = results.video_results(session, selected.id)
    job = jobs.get_job(session, found.job_id) if found and found.job_id is not None else None
    cards = overall if scope == "all" else metrics.summary(session, selected.id)
    recent = results.video_detections(session, selected.id, limit=RECENT_LIMIT)
    return Overview(
        processed, selected, cards, scope if scope in ("video", "all") else "video", overall, found, job, recent
    )
