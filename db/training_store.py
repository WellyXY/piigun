"""PostgreSQL CRUD for LoRA training jobs."""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from db.job_store import get_pool

logger = logging.getLogger(__name__)


async def create_training_job(
    position: str,
    r2_prefix: str,
    config: dict,
) -> dict:
    pool = await get_pool()
    job_id = str(uuid.uuid4())
    now = time.time()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO training_jobs (id, position, status, r2_prefix, config, created_at)
            VALUES ($1, $2, 'provisioning', $3, $4, $5)
            """,
            job_id, position, r2_prefix, json.dumps(config), now,
        )
    return await get_training_job(job_id)


async def create_training_job_with_id(
    job_id: str,
    position: str,
    r2_prefix: str,
    config: dict,
) -> dict:
    pool = await get_pool()
    now = time.time()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO training_jobs (id, position, status, r2_prefix, config, created_at)
            VALUES ($1, $2, 'provisioning', $3, $4, $5)
            """,
            job_id, position, r2_prefix, json.dumps(config), now,
        )
    return await get_training_job(job_id)


async def get_training_job(job_id: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM training_jobs WHERE id = $1", job_id
        )
    if not row:
        return None
    return dict(row)


async def list_training_jobs(limit: int = 50) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM training_jobs ORDER BY created_at DESC LIMIT $1", limit
        )
    return [dict(r) for r in rows]


async def update_training_job(job_id: str, **kwargs) -> None:
    """Update any subset of fields. Supported: status, pod_id, pod_ip,
    current_step, total_steps, error, completed_at."""
    if not kwargs:
        return
    pool = await get_pool()
    set_parts = []
    values = []
    for i, (k, v) in enumerate(kwargs.items(), start=1):
        set_parts.append(f"{k} = ${i}")
        values.append(v)
    values.append(job_id)
    sql = f"UPDATE training_jobs SET {', '.join(set_parts)} WHERE id = ${len(values)}"
    async with pool.acquire() as conn:
        await conn.execute(sql, *values)
