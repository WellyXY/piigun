"""
GPU Worker — one process per GPU on RunPod.

Startup:
  1. Load base model into VRAM
  2. Pre-load Fast LoRA
  3. Main loop: BRPOP from Redis queue, run inference, upload to R2, write to PG

Usage:
  python -m workers.gpu_worker --gpu_id 0
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import time

import redis.asyncio as aioredis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.config import settings
from api.models import JobStatus
from task_queue.job_manager import get_job, pop_job, update_job
from webhook.sender import send_webhook
from workers.inference_engine import InferenceEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GPU%(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SHUTDOWN = False


def handle_signal(sig, frame):
    global SHUTDOWN
    logger.info("Shutdown signal received, finishing current job...")
    SHUTDOWN = True


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


async def _upload_to_r2(job_id: str, video_path: str) -> str:
    """Upload video to R2. Returns public URL."""
    from storage.r2_storage import upload_video
    return await asyncio.to_thread(upload_video, job_id, video_path)


async def _write_pg_complete(job_id: str, video_url: str, completed_at: float, started_at: float):
    if not settings.DATABASE_URL:
        return
    try:
        from db import job_store
        await job_store.complete_job(job_id, video_url, completed_at, started_at)
    except Exception as e:
        logger.warning(f"PG complete write failed for {job_id}: {e}")


async def _write_pg_fail(job_id: str, error: str, completed_at: float, started_at: float = 0):
    if not settings.DATABASE_URL:
        return
    try:
        from db import job_store
        await job_store.fail_job(job_id, error, completed_at, started_at)
    except Exception as e:
        logger.warning(f"PG fail write failed for {job_id}: {e}")


async def process_job(engine: InferenceEngine, r: aioredis.Redis, job_id: str):
    job = await get_job(r, job_id)
    if not job:
        logger.warning(f" {engine.gpu_id}] Job {job_id} not found, skipping")
        return

    now = time.time()
    wait_time = now - float(job.get("created_at", 0))
    if wait_time > settings.QUEUE_EXPIRE_SECONDS:
        error_msg = f"Queue timeout: waited {wait_time:.0f}s"
        await update_job(r, job_id, status=JobStatus.FAILED.value,
                         error=error_msg, completed_at=now)
        await _write_pg_fail(job_id, error_msg, now)

        if job.get("callback_url"):
            await send_webhook(job["callback_url"], {
                "event": "job.expired", "job_id": job_id, "error": error_msg,
            })
        return

    position = job["position"]
    started_at = time.time()
    logger.info(f" {engine.gpu_id}] Processing {job_id}: position={position} (waited {wait_time:.0f}s)")

    await update_job(r, job_id, status=JobStatus.PROCESSING.value,
                     started_at=started_at, progress=0.1)

    try:
        # Download input image from R2 to a local temp file
        import tempfile
        import httpx as _httpx
        image_url = job.get("image_url") or job.get("image_path", "")
        tmp_image = tempfile.NamedTemporaryFile(suffix=".webp", delete=False)
        tmp_image_path = tmp_image.name
        tmp_image.close()
        async with _httpx.AsyncClient(timeout=30) as _client:
            _resp = await _client.get(image_url)
            _resp.raise_for_status()
        with open(tmp_image_path, "wb") as _f:
            _f.write(_resp.content)

        raw_video_path, gen_time = engine.generate(
            position=position,
            image_path=tmp_image_path,
            prompt=job.get("prompt", ""),
            duration=int(job.get("duration", 10)),
            seed=int(job.get("seed", 42)),
            include_audio=job.get("include_audio", "false").lower() == "true",
            audio_description=job.get("audio_description", ""),
        )
        try:
            os.unlink(tmp_image_path)
        except Exception:
            pass
        await update_job(r, job_id, progress=0.7)

        # server.py already handles GFPGAN enhancement
        final_path = raw_video_path
        pp_time = 0.0

        # Upload to Cloudflare R2
        await update_job(r, job_id, progress=0.9)
        video_url = await _upload_to_r2(job_id, final_path)

        if os.path.isfile(final_path):
            os.unlink(final_path)

        completed_at = time.time()
        await update_job(r, job_id,
                         status=JobStatus.COMPLETED.value,
                         progress=1.0,
                         completed_at=completed_at,
                         video_url=video_url)

        await _write_pg_complete(job_id, video_url, completed_at, started_at)

        from api.auth import increment_usage
        await increment_usage(job["api_key_hash"], "completed_jobs")

        logger.info(
            f" {engine.gpu_id}] Completed {job_id}: "
            f"gen={gen_time:.1f}s, pp={pp_time:.1f}s, total={gen_time + pp_time:.1f}s"
        )

        if job.get("callback_url"):
            await send_webhook(job["callback_url"], {
                "event": "job.completed",
                "job_id": job_id,
                "video_url": video_url,
                "metadata": {
                    "position": position,
                    "duration": int(job.get("duration", 10)),
                    "resolution": settings.OUTPUT_RESOLUTION,
                    "fps": settings.OUTPUT_FPS,
                },
            })

    except Exception as e:
        completed_at = time.time()
        logger.error(f" {engine.gpu_id}] Job {job_id} failed: {e}", exc_info=True)
        await update_job(r, job_id, status=JobStatus.FAILED.value,
                         error=str(e), completed_at=completed_at)
        await _write_pg_fail(job_id, str(e), completed_at, started_at)

        from api.auth import increment_usage
        await increment_usage(job["api_key_hash"], "failed_jobs")

        if job.get("callback_url"):
            await send_webhook(job["callback_url"], {
                "event": "job.failed", "job_id": job_id, "error": str(e),
            })


async def main_loop(gpu_id: int):
    logger.info(f" {gpu_id}] Starting GPU worker")

    engine = InferenceEngine(
        gpu_id=gpu_id,
        model_path=settings.BASE_MODEL_PATH,
        lora_dir=settings.LORA_DIR,
        fast_lora_dir=settings.FAST_LORA_DIR,
    )
    engine.startup()

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.ping()
    logger.info(f" {gpu_id}] Connected to Redis at {settings.REDIS_URL}")

    while not SHUTDOWN:
        try:
            job_id = await pop_job(r, timeout=5)
            if job_id is None:
                continue
            await process_job(engine, r, job_id)
        except Exception as e:
            logger.error(f" {gpu_id}] Main loop error: {e}", exc_info=True)
            await asyncio.sleep(2)

    logger.info(f" {gpu_id}] Worker shut down cleanly")
    await r.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu_id", type=int, required=True)
    args = parser.parse_args()

    os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu_id)
    asyncio.run(main_loop(args.gpu_id))
