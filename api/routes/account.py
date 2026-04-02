from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.auth import get_redis, verify_api_key
from api.config import settings
from api.models import AccountJobItem, AccountJobsResponse, AccountUsageResponse

router = APIRouter()


@router.get("/account/usage", response_model=AccountUsageResponse)
async def get_usage(key_hash: str = Depends(verify_api_key)):
    r = await get_redis()
    data = await r.hgetall(f"apikey:{key_hash}")
    month = datetime.utcnow().strftime("%Y-%m")

    credits = 0.0
    credits_used = 0.0
    if settings.DATABASE_URL:
        from db import job_store
        pg = await job_store.get_api_key(key_hash)
        if pg:
            credits = float(pg["credits"])
            credits_used = float(pg["credits_used"])

    return AccountUsageResponse(
        api_key=data.get("name", "unknown"),
        credits=credits,
        credits_used=credits_used,
        total_jobs=int(data.get("total_jobs", 0)),
        completed_jobs=int(data.get("completed_jobs", 0)),
        failed_jobs=int(data.get("failed_jobs", 0)),
        month=month,
    )


@router.get("/account/jobs", response_model=AccountJobsResponse)
async def get_my_jobs(
    key_hash: str = Depends(verify_api_key),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
):
    from db import job_store
    jobs, total = await job_store.get_key_jobs(key_hash, page, limit, status)

    items = [
        AccountJobItem(
            job_id=j["job_id"],
            position=j["position"],
            duration=int(j["duration"]),
            status=j["status"],
            credits_charged=float(j.get("credits_charged") or 0),
            video_url=j.get("video_url") or None,
            created_at=float(j["created_at"]),
            completed_at=float(j["completed_at"]) if j.get("completed_at") else None,
            prompt=j.get("prompt", ""),
            seed=int(j.get("seed", 0)),
            callback_url=j.get("callback_url", ""),
        )
        for j in jobs
    ]
    return AccountJobsResponse(jobs=items, total=total, page=page, limit=limit)
