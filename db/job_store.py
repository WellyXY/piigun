"""
PostgreSQL persistence for job records.
Used by the gateway (create + fallback read) and worker (complete/fail write).
"""
from __future__ import annotations

import logging
from typing import Optional

import asyncpg

from api.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    api_key_hash    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    position        TEXT NOT NULL,
    prompt          TEXT NOT NULL DEFAULT '',
    duration        INTEGER NOT NULL DEFAULT 10,
    seed            INTEGER NOT NULL DEFAULT 0,
    video_url       TEXT,
    error           TEXT,
    created_at      DOUBLE PRECISION NOT NULL,
    started_at      DOUBLE PRECISION,
    completed_at    DOUBLE PRECISION,
    callback_url    TEXT NOT NULL DEFAULT ''
);
"""


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
        async with _pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
        logger.info("[DB] PostgreSQL pool ready")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def save_job(job: dict):
    """Insert a new job record (called by gateway on job creation)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO jobs
                (job_id, api_key_hash, status, position, prompt, duration, seed,
                 created_at, callback_url)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (job_id) DO NOTHING
            """,
            job["job_id"],
            job["api_key_hash"],
            job["status"],
            job["position"],
            job.get("prompt", ""),
            int(job.get("duration", 10)),
            int(job.get("seed", 0)),
            float(job["created_at"]),
            job.get("callback_url", ""),
        )


async def complete_job(job_id: str, video_url: str, completed_at: float, started_at: float):
    """Mark job as completed with R2 video URL (called by worker)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE jobs
            SET status = 'completed', video_url = $2,
                started_at = $3, completed_at = $4
            WHERE job_id = $1
            """,
            job_id, video_url, started_at, completed_at,
        )


async def fail_job(job_id: str, error: str, completed_at: float, started_at: float = 0):
    """Mark job as failed (called by worker)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE jobs
            SET status = 'failed', error = $2,
                started_at = CASE WHEN $3 > 0 THEN $3 ELSE started_at END,
                completed_at = $4
            WHERE job_id = $1
            """,
            job_id, error, started_at, completed_at,
        )


async def get_job(job_id: str) -> Optional[dict]:
    """Fetch a job from PostgreSQL (fallback when Redis TTL has expired)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM jobs WHERE job_id = $1", job_id
        )
    if not row:
        return None
    return dict(row)
