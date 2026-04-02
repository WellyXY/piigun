"""
PostgreSQL persistence for job records and API key management.
Used by the gateway (create + fallback read) and worker (complete/fail/deduct write).
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

CREATE_API_KEYS_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    key_hash        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    created_at      DOUBLE PRECISION NOT NULL,
    disabled        BOOLEAN NOT NULL DEFAULT FALSE,
    credits         NUMERIC(12,4) NOT NULL DEFAULT 0,
    credits_used    NUMERIC(12,4) NOT NULL DEFAULT 0,
    total_jobs      INTEGER NOT NULL DEFAULT 0,
    completed_jobs  INTEGER NOT NULL DEFAULT 0,
    failed_jobs     INTEGER NOT NULL DEFAULT 0
);
"""

ADD_CREDITS_CHARGED_SQL = """
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS credits_charged NUMERIC(12,4) DEFAULT 0;
"""

ADD_RAW_KEY_SQL = """
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS raw_key TEXT DEFAULT '';
"""


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
        async with _pool.acquire() as conn:
            await conn.execute(CREATE_TABLE_SQL)
            await conn.execute(CREATE_API_KEYS_SQL)
            await conn.execute(ADD_CREDITS_CHARGED_SQL)
            await conn.execute(ADD_RAW_KEY_SQL)
        logger.info("[DB] PostgreSQL pool ready")
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── Job CRUD ──────────────────────────────────────────────────────────────────

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


async def get_jobs_paginated(
    page: int,
    limit: int,
    key_hash: Optional[str] = None,
    status: Optional[str] = None,
) -> tuple[list[dict], int]:
    """Admin: paginated job list with optional filters."""
    pool = await get_pool()
    conditions = []
    params: list = []
    idx = 1

    if key_hash:
        conditions.append(f"j.api_key_hash = ${idx}")
        params.append(key_hash)
        idx += 1
    if status:
        conditions.append(f"j.status = ${idx}")
        params.append(status)
        idx += 1

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM jobs j {where}", *params
        )
        rows = await conn.fetch(
            f"""
            SELECT j.job_id, j.api_key_hash, j.status, j.position, j.prompt,
                   j.duration, j.seed, j.video_url, j.error,
                   j.created_at, j.started_at, j.completed_at, j.callback_url,
                   COALESCE(j.credits_charged, 0) as credits_charged,
                   k.name as key_name
            FROM jobs j
            LEFT JOIN api_keys k ON j.api_key_hash = k.key_hash
            {where}
            ORDER BY j.created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, (page - 1) * limit,
        )
    return [dict(r) for r in rows], total


async def get_key_jobs(
    key_hash: str,
    page: int,
    limit: int,
    status: Optional[str] = None,
) -> tuple[list[dict], int]:
    """User: paginated job list for a specific key."""
    pool = await get_pool()
    conditions = ["api_key_hash = $1"]
    params: list = [key_hash]
    idx = 2

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = "WHERE " + " AND ".join(conditions)

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM jobs {where}", *params
        )
        rows = await conn.fetch(
            f"""
            SELECT job_id, position, duration, status,
                   COALESCE(credits_charged, 0) as credits_charged,
                   video_url, created_at, completed_at, prompt, seed, callback_url
            FROM jobs {where}
            ORDER BY created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, (page - 1) * limit,
        )
    return [dict(r) for r in rows], total


# ── API Key CRUD ──────────────────────────────────────────────────────────────

async def upsert_api_key(key_hash: str, name: str, created_at: float, credits: float = 0.0, raw_key: str = ""):
    """Insert a new API key. No-op if already exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO api_keys (key_hash, name, created_at, credits, raw_key)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (key_hash) DO NOTHING
            """,
            key_hash, name, created_at, credits, raw_key,
        )


async def get_api_key(key_hash: str) -> Optional[dict]:
    """Fetch key metadata from PostgreSQL."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM api_keys WHERE key_hash = $1", key_hash
        )
    if not row:
        return None
    return dict(row)


async def list_api_keys() -> list[dict]:
    """List all API keys ordered by creation date (newest first)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM api_keys ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


async def update_api_key(
    key_hash: str,
    *,
    disabled: Optional[bool] = None,
    add_credits: Optional[float] = None,
):
    """Admin: disable/enable key or top up credits."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if disabled is not None:
            await conn.execute(
                "UPDATE api_keys SET disabled = $1 WHERE key_hash = $2",
                disabled, key_hash,
            )
        if add_credits is not None:
            await conn.execute(
                "UPDATE api_keys SET credits = credits + $1 WHERE key_hash = $2",
                add_credits, key_hash,
            )


async def check_credits(key_hash: str) -> float:
    """Return current credits balance. Returns -1.0 if key not found in PG."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT credits FROM api_keys WHERE key_hash = $1", key_hash
        )
    if not row:
        return -1.0
    return float(row["credits"])


async def deduct_credits(key_hash: str, amount: float, job_id: str) -> bool:
    """
    Atomically deduct credits on job completion.
    Returns True if successful, False if balance is insufficient.
    Also writes credits_charged to the jobs table.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE api_keys
                SET credits = credits - $1,
                    credits_used = credits_used + $1,
                    completed_jobs = completed_jobs + 1
                WHERE key_hash = $2 AND credits >= $1
                RETURNING credits
                """,
                amount, key_hash,
            )
            if row is None:
                return False
            await conn.execute(
                "UPDATE jobs SET credits_charged = $1 WHERE job_id = $2",
                amount, job_id,
            )
            return True


async def increment_api_key_jobs(key_hash: str, field: str):
    """Increment total_jobs or failed_jobs counter."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Only allow safe field names
        if field not in ("total_jobs", "failed_jobs", "completed_jobs"):
            return
        await conn.execute(
            f"UPDATE api_keys SET {field} = {field} + 1 WHERE key_hash = $1",
            key_hash,
        )
