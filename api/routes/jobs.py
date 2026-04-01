from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from api.auth import get_redis, verify_api_key
from api.config import settings
from api.models import JobMetadata, JobResponse, JobStatus
from db import job_store
from task_queue.job_manager import cancel_job, get_job

router = APIRouter()


def _ts_to_iso(ts: float) -> Optional[str]:
    if not ts or ts == 0:
        return None
    return datetime.utcfromtimestamp(ts).isoformat() + "Z"


def _build_video_url(job_id: str, video_url: str) -> Optional[str]:
    """Return R2 URL if available, else the download endpoint URL."""
    if video_url and video_url.startswith("https://"):
        return video_url
    if video_url:
        return f"{settings.VIDEO_BASE_URL}/{job_id}/video"
    return None


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    key_hash: str = Depends(verify_api_key),
):
    r = await get_redis()

    # 1. Try Redis (hot path)
    job = await get_job(r, job_id)

    # 2. Fall back to PostgreSQL (after Redis TTL expires)
    if not job and settings.DATABASE_URL:
        try:
            job = await job_store.get_job(job_id)
        except Exception:
            pass

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("api_key_hash") != key_hash:
        raise HTTPException(status_code=403, detail="Access denied")

    status = job["status"]
    video_url = _build_video_url(job_id, job.get("video_url") or "")

    return JobResponse(
        job_id=job_id,
        status=status,
        progress=float(job.get("progress", 0)),
        created_at=_ts_to_iso(float(job.get("created_at", 0))) or "",
        started_at=_ts_to_iso(float(job.get("started_at", 0) or 0)),
        completed_at=_ts_to_iso(float(job.get("completed_at", 0) or 0)),
        video_url=video_url,
        error=job.get("error") or None,
        metadata=JobMetadata(
            position=job["position"],
            duration=int(job.get("duration", 10)),
            prompt=job.get("prompt", ""),
        ),
    )


@router.get("/jobs/{job_id}/video")
async def download_video(
    job_id: str,
    key_hash: str = Depends(verify_api_key),
):
    r = await get_redis()
    job = await get_job(r, job_id)

    if not job and settings.DATABASE_URL:
        try:
            job = await job_store.get_job(job_id)
        except Exception:
            pass

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("api_key_hash") != key_hash:
        raise HTTPException(status_code=403, detail="Access denied")
    if job["status"] != JobStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Video not ready yet")

    video_url = job.get("video_url", "")
    if not video_url:
        raise HTTPException(status_code=404, detail="Video file not found")

    # If video is on R2, redirect directly — no proxying through Railway
    if video_url.startswith("https://"):
        return RedirectResponse(url=video_url, status_code=302)

    raise HTTPException(status_code=404, detail="Video file not found")


@router.delete("/jobs/{job_id}")
async def cancel_job_endpoint(
    job_id: str,
    key_hash: str = Depends(verify_api_key),
):
    r = await get_redis()
    job = await get_job(r, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("api_key_hash") != key_hash:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await cancel_job(r, job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel job in current state")

    return {"job_id": job_id, "status": "cancelled"}
