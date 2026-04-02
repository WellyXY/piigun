from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from fastapi import Depends, Header, HTTPException, Security
from fastapi.security import APIKeyHeader

from api.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_redis: Optional[aioredis.Redis] = None

CACHE_TTL = 60  # seconds


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def _cache_key_data(r: aioredis.Redis, key_hash: str, data: dict):
    """Write key metadata to Redis cache with TTL."""
    await r.hset(f"apikey:{key_hash}", mapping={
        "name": str(data.get("name", "")),
        "disabled": "1" if data.get("disabled") else "0",
        "credits": str(data.get("credits", 0)),
        "total_jobs": str(data.get("total_jobs", 0)),
        "completed_jobs": str(data.get("completed_jobs", 0)),
        "failed_jobs": str(data.get("failed_jobs", 0)),
    })
    await r.expire(f"apikey:{key_hash}", CACHE_TTL)


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    r = await get_redis()
    key_hash = hash_key(api_key)

    # Try Redis cache first (only if TTL > 0 meaning it was cached by us)
    cache_ttl = await r.ttl(f"apikey:{key_hash}")
    if cache_ttl > 0:
        key_data = await r.hgetall(f"apikey:{key_hash}")
        if key_data:
            if key_data.get("disabled") == "1":
                raise HTTPException(status_code=403, detail="API key disabled")
            return key_hash

    # Cache miss — query PostgreSQL if available
    if settings.DATABASE_URL:
        from db import job_store
        pg_data = await job_store.get_api_key(key_hash)
        if not pg_data:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if pg_data.get("disabled"):
            raise HTTPException(status_code=403, detail="API key disabled")
        await _cache_key_data(r, key_hash, pg_data)
        return key_hash

    # Fallback: legacy Redis-only mode (for keys created before PG migration)
    key_data = await r.hgetall(f"apikey:{key_hash}")
    if not key_data:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if key_data.get("disabled") == "1":
        raise HTTPException(status_code=403, detail="API key disabled")
    return key_hash


async def create_api_key(name: str, credits: float = 0.0) -> str:
    """Create a new API key — writes to PostgreSQL and Redis."""
    raw_key = f"pk_{secrets.token_urlsafe(32)}"
    key_hash = hash_key(raw_key)
    now = time.time()

    if settings.DATABASE_URL:
        from db import job_store
        await job_store.upsert_api_key(key_hash, name, now, credits, raw_key=raw_key)

    # Also write to Redis set (for monthly usage counters) and cache
    r = await get_redis()
    await r.sadd("apikeys", key_hash)
    await _cache_key_data(r, key_hash, {
        "name": name,
        "disabled": False,
        "credits": credits,
        "total_jobs": 0,
        "completed_jobs": 0,
        "failed_jobs": 0,
    })

    return raw_key


async def increment_usage(key_hash: str, field: str = "total_jobs"):
    """Increment Redis usage counters and invalidate cache."""
    r = await get_redis()
    await r.hincrby(f"apikey:{key_hash}", field, 1)
    month = datetime.utcnow().strftime("%Y-%m")
    await r.hincrby(f"apikey:{key_hash}:usage:{month}", "count", 1)
    # Invalidate cache so next verify re-reads fresh data from PG
    await r.expire(f"apikey:{key_hash}", 1)


async def require_admin(x_admin_password: Optional[str] = Header(default=None)):
    """FastAPI dependency for admin routes — validates X-Admin-Password header."""
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD not configured on server")
    if not x_admin_password:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Password header")
    if x_admin_password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Invalid admin password")
