from __future__ import annotations

import time
import uuid
from typing import Optional

import redis.asyncio as aioredis

from api.config import settings
from api.models import JobStatus

JOB_PREFIX = "job:"
QUEUE_KEY = "job_queue"


def _job_key(job_id: str) -> str:
    return f"{JOB_PREFIX}{job_id}"


async def create_job(
    r: aioredis.Redis,
    *,
    position: str,
    prompt: str,
    duration: int,
    seed: Optional[int],
    image_url: str,
    callback_url: Optional[str],
    api_key_hash: str,
    include_audio: bool = False,
    audio_description: str = "",
    nsfw_weight: Optional[float] = None,
    motion_weight: Optional[float] = None,
    position_weight: Optional[float] = None,
) -> dict:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = time.time()

    job = {
        "job_id": job_id,
        "status": JobStatus.QUEUED.value,
        "progress": 0.0,
        "position": position,
        "prompt": prompt or "",
        "duration": duration,
        "seed": seed if seed is not None else int(now) % 100000,
        "image_url": image_url,
        "callback_url": callback_url or "",
        "api_key_hash": api_key_hash,
        "include_audio": include_audio,
        "audio_description": audio_description,
        "nsfw_weight": nsfw_weight if nsfw_weight is not None else "",
        "motion_weight": motion_weight if motion_weight is not None else "",
        "position_weight": position_weight if position_weight is not None else "",
        "created_at": now,
        "started_at": 0,
        "completed_at": 0,
        "video_url": "",
        "error": "",
    }

    await r.hset(_job_key(job_id), mapping={k: str(v) for k, v in job.items()})
    await r.expire(_job_key(job_id), settings.JOB_TTL_HOURS * 3600)
    await r.lpush(QUEUE_KEY, job_id)

    return job


async def get_job(r: aioredis.Redis, job_id: str) -> Optional[dict]:
    data = await r.hgetall(_job_key(job_id))
    if not data:
        return None
    data["progress"] = float(data.get("progress", 0))
    data["created_at"] = float(data.get("created_at", 0))
    data["started_at"] = float(data.get("started_at", 0))
    data["completed_at"] = float(data.get("completed_at", 0))
    return data


async def update_job(r: aioredis.Redis, job_id: str, **fields):
    if fields:
        await r.hset(_job_key(job_id), mapping={k: str(v) for k, v in fields.items()})


async def get_queue_length(r: aioredis.Redis) -> int:
    return await r.llen(QUEUE_KEY)


async def get_queue_position(r: aioredis.Redis, job_id: str) -> int:
    items = await r.lrange(QUEUE_KEY, 0, -1)
    try:
        return items.index(job_id) + 1
    except ValueError:
        return 0


async def pop_job(r: aioredis.Redis, timeout: int = 0) -> Optional[str]:
    result = await r.brpop(QUEUE_KEY, timeout=timeout)
    if result:
        return result[1]
    return None


async def cancel_job(r: aioredis.Redis, job_id: str) -> bool:
    job = await get_job(r, job_id)
    if not job:
        return False
    if job["status"] not in (JobStatus.QUEUED.value,):
        return False

    await r.lrem(QUEUE_KEY, 1, job_id)
    await update_job(r, job_id, status=JobStatus.CANCELLED.value)
    return True
