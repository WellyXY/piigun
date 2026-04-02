from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import create_api_key, get_redis, require_admin
from api.models import (
    AdminJobItem,
    AdminJobsResponse,
    AdminKeyItem,
    CreateKeyRequest,
    DisableKeyRequest,
    TopUpRequest,
)

router = APIRouter(prefix="/v1/admin", dependencies=[Depends(require_admin)])


@router.post("/keys")
async def create_key(req: CreateKeyRequest):
    key = await create_api_key(req.name, req.credits)
    return {"name": req.name, "api_key": key, "credits": req.credits}


@router.get("/keys")
async def list_keys():
    from db import job_store
    keys = await job_store.list_api_keys()
    return {
        "keys": [
            AdminKeyItem(
                key_hash=k["key_hash"],
                name=k["name"],
                created_at=float(k["created_at"]),
                disabled=bool(k["disabled"]),
                credits=float(k["credits"]),
                credits_used=float(k["credits_used"]),
                total_jobs=int(k["total_jobs"]),
                completed_jobs=int(k["completed_jobs"]),
                failed_jobs=int(k["failed_jobs"]),
                raw_key=k.get("raw_key") or "",
            )
            for k in keys
        ]
    }


@router.patch("/keys/{key_hash}/topup")
async def topup_credits(key_hash: str, req: TopUpRequest):
    if req.add_credits <= 0:
        raise HTTPException(status_code=400, detail="add_credits must be positive")
    from db import job_store
    await job_store.update_api_key(key_hash, add_credits=req.add_credits)
    # Invalidate Redis cache so next request re-reads fresh balance
    r = await get_redis()
    await r.expire(f"apikey:{key_hash}", 1)
    return {"ok": True, "added": req.add_credits}


@router.patch("/keys/{key_hash}/disable")
async def set_key_disabled(key_hash: str, req: DisableKeyRequest):
    from db import job_store
    await job_store.update_api_key(key_hash, disabled=req.disabled)
    r = await get_redis()
    await r.expire(f"apikey:{key_hash}", 1)
    return {"ok": True, "disabled": req.disabled}


@router.get("/jobs", response_model=AdminJobsResponse)
async def list_jobs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    key_hash: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    from db import job_store
    jobs, total = await job_store.get_jobs_paginated(page, limit, key_hash, status)
    def _runtime(j: dict) -> Optional[float]:
        s = j.get("started_at")
        c = j.get("completed_at")
        if s and c:
            return round(float(c) - float(s), 1)
        return None

    items = [
        AdminJobItem(
            job_id=j["job_id"],
            key_name=j.get("key_name"),
            api_key_hash=j["api_key_hash"],
            position=j["position"],
            duration=int(j["duration"]),
            status=j["status"],
            credits_charged=float(j.get("credits_charged") or 0),
            video_url=j.get("video_url") or None,
            created_at=float(j["created_at"]),
            started_at=float(j["started_at"]) if j.get("started_at") else None,
            completed_at=float(j["completed_at"]) if j.get("completed_at") else None,
            runtime_seconds=_runtime(j),
            prompt=j.get("prompt", ""),
            seed=int(j.get("seed", 0)),
            callback_url=j.get("callback_url", ""),
        )
        for j in jobs
    ]
    return AdminJobsResponse(jobs=items, total=total, page=page, limit=limit)


@router.get("/billing")
async def billing_report(month: Optional[str] = None):
    r = await get_redis()
    if not month:
        month = datetime.utcnow().strftime("%Y-%m")

    from db import job_store
    keys = await job_store.list_api_keys()
    report = []
    for k in keys:
        kh = k["key_hash"]
        usage = await r.hgetall(f"apikey:{kh}:usage:{month}")
        count = int(usage.get("count", 0))
        report.append({
            "name": k["name"],
            "key_hash_prefix": kh[:12],
            "month": month,
            "jobs_this_month": count,
            "total_jobs": int(k["total_jobs"]),
            "completed_jobs": int(k["completed_jobs"]),
            "failed_jobs": int(k["failed_jobs"]),
            "credits": float(k["credits"]),
            "credits_used": float(k["credits_used"]),
            "status": "disabled" if k["disabled"] else "active",
        })

    return {
        "month": month,
        "total_clients": len(report),
        "total_jobs_this_month": sum(r_["jobs_this_month"] for r_ in report),
        "total_credits_used": sum(r_["credits_used"] for r_ in report),
        "clients": report,
    }


@router.post("/simulate-complete")
async def simulate_job_complete(job_id: str):
    """
    TEST ONLY: Simulate a job completing successfully.
    Marks job as completed in Redis and deducts credits from PG.
    Used for integration testing when GPU is unavailable.
    """
    r = await get_redis()
    from task_queue.job_manager import get_job, update_job
    from api.models import JobStatus

    job = await get_job(r, job_id)
    if not job:
        # Try PostgreSQL fallback
        from db import job_store
        pg_job = await job_store.get_job(job_id)
        if not pg_job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        # Simulate using PG data
        key_hash = pg_job["api_key_hash"]
        duration = int(pg_job.get("duration", 10))
    else:
        key_hash = job["api_key_hash"]
        duration = int(job.get("duration", 10))

    now = time.time()
    started_at = now - duration  # pretend it ran for `duration` seconds

    # Update Redis
    await update_job(r, job_id,
        status=JobStatus.COMPLETED.value,
        progress=1.0,
        started_at=started_at,
        completed_at=now,
        video_url="https://example.com/simulated-video.mp4",
    )

    # Update PostgreSQL
    from db import job_store
    await job_store.complete_job(job_id, "https://example.com/simulated-video.mp4", now, started_at)

    # Deduct credits
    cost = duration * __import__("api.config", fromlist=["settings"]).settings.CREDITS_PER_SECOND
    ok = await job_store.deduct_credits(key_hash, cost, job_id)

    return {
        "job_id": job_id,
        "simulated": True,
        "credits_deducted": cost,
        "deduction_ok": ok,
        "key_hash": key_hash[:12] + "...",
    }


@router.post("/cleanup")
async def cleanup_expired_jobs(max_age_hours: int = 24):
    """Remove completed/failed jobs older than max_age_hours from Redis."""
    r = await get_redis()
    cutoff = time.time() - (max_age_hours * 3600)
    cleaned = 0
    cursor = 0
    while True:
        cursor, keys = await r.scan(cursor, match="job:job_*", count=100)
        for key in keys:
            data = await r.hgetall(key)
            status = data.get("status", "")
            completed_at = float(data.get("completed_at", 0))
            if status in ("completed", "failed", "cancelled") and completed_at > 0 and completed_at < cutoff:
                await r.delete(key)
                cleaned += 1
        if cursor == 0:
            break
    return {"cleaned_jobs": cleaned, "cutoff_hours": max_age_hours}
