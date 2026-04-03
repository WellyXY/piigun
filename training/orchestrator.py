"""
Background orchestrator for a single training job lifecycle:
  provisioning → preprocessing → training → uploading → done (or failed)

Called as an asyncio task per job. Communicates with the pod agent via HTTP.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

from api.config import settings
from db import training_store
from training import runpod_client
from training.config_generator import build_jsonl_manifest, build_yaml_config

logger = logging.getLogger(__name__)

POLL_INTERVAL = 15       # seconds between RunPod status polls
POD_READY_TIMEOUT = 600  # 10 minutes max wait for pod to be RUNNING
AGENT_READY_TIMEOUT = 120  # 2 minutes for agent to respond after pod is RUNNING


def _agent_headers() -> dict:
    return {"X-Agent-Secret": settings.AGENT_SECRET, "Content-Type": "application/json"}


async def _wait_for_pod_running(pod_id: str) -> dict:
    """Poll RunPod until pod status is RUNNING. Returns pod dict with public URL."""
    deadline = time.time() + POD_READY_TIMEOUT
    while time.time() < deadline:
        pod = await runpod_client.get_pod(pod_id)
        status = pod.get("status", "")
        logger.info(f"[Orch] Pod {pod_id} status: {status}")
        if status == "RUNNING":
            return pod
        if status in ("EXITED", "FAILED", "TERMINATED"):
            raise RuntimeError(f"Pod {pod_id} entered terminal state: {status}")
        await asyncio.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Pod {pod_id} did not become RUNNING within {POD_READY_TIMEOUT}s")


async def _wait_for_agent(agent_url: str) -> None:
    """Poll agent /status until it responds."""
    deadline = time.time() + AGENT_READY_TIMEOUT
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{agent_url}/status",
                    headers=_agent_headers(),
                )
                if resp.status_code == 200:
                    logger.info(f"[Orch] Agent is ready at {agent_url}")
                    return
        except Exception:
            pass
        await asyncio.sleep(10)
    raise TimeoutError(f"Agent at {agent_url} did not respond within {AGENT_READY_TIMEOUT}s")


async def _call_agent(agent_url: str, method: str, path: str, body: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        fn = client.post if method == "POST" else client.get
        kwargs = {"headers": _agent_headers()}
        if body is not None:
            kwargs["json"] = body
        resp = await fn(f"{agent_url}{path}", **kwargs)
        resp.raise_for_status()
        return resp.json()


async def _poll_training_progress(agent_url: str, job_id: str) -> None:
    """
    Poll agent /status every 30s and update PG step count.
    Returns when training is complete (phase == 'done') or raises on failure.
    """
    while True:
        try:
            data = await _call_agent(agent_url, "GET", "/status")
            phase = data.get("phase", "")
            step = int(data.get("current_step", 0))
            total = int(data.get("total_steps", 2000))

            await training_store.update_training_job(job_id, current_step=step, total_steps=total)
            logger.info(f"[Orch] Job {job_id}: {phase} step={step}/{total}")

            if phase == "done":
                return
            if phase == "failed":
                raise RuntimeError(data.get("error", "Training failed"))
        except httpx.HTTPError as e:
            logger.warning(f"[Orch] Agent poll error: {e}")

        await asyncio.sleep(30)


async def start_job_orchestration(job_id: str) -> None:
    """
    Full lifecycle for one training job. Run as asyncio.create_task().
    Pod is managed externally — user provides pod_url, we just connect to the agent.
    """
    job = await training_store.get_training_job(job_id)
    if not job:
        logger.error(f"[Orch] Job {job_id} not found")
        return

    config = job["config"] if isinstance(job["config"], dict) else json.loads(job["config"])
    position = job["position"]
    r2_prefix = job["r2_prefix"]
    agent_url = config.get("pod_url", "").rstrip("/")

    if not agent_url:
        await training_store.update_training_job(
            job_id, status="failed", error="pod_url not set in job config", completed_at=time.time()
        )
        return

    try:
        # ── 1. Record agent URL and wait for it to respond ────────────
        await training_store.update_training_job(job_id, pod_ip=agent_url, status="provisioning")
        logger.info(f"[Orch] Connecting to agent at {agent_url}")
        await _wait_for_agent(agent_url)

        # ── 2. Download videos from R2, write config files ────────────
        await training_store.update_training_job(job_id, status="preprocessing")
        videos = config.get("videos", [])
        video_r2_keys = [f"{r2_prefix}/videos/{v['filename']}" for v in videos]

        yaml_config = build_yaml_config(job_id, position, config)
        jsonl_manifest = build_jsonl_manifest([
            {
                "path": f"/workspace/training/{job_id}_videos/{v['filename']}",
                "caption": v["caption"],
            }
            for v in videos
        ])

        await _call_agent(agent_url, "POST", "/setup", {
            "job_id": job_id,
            "r2_video_keys": video_r2_keys,
            "yaml_config": yaml_config,
            "jsonl_manifest": jsonl_manifest,
            "frames": config.get("frames", 249),
        })

        # ── 3. Start training ─────────────────────────────────────────
        await _call_agent(agent_url, "POST", "/train", {})
        await training_store.update_training_job(job_id, status="training")

        # ── 4. Poll progress ──────────────────────────────────────────
        await _poll_training_progress(agent_url, job_id)

        # ── 5. Upload checkpoints to R2 ───────────────────────────────
        await training_store.update_training_job(job_id, status="uploading")
        await _call_agent(agent_url, "POST", "/upload-checkpoints", {
            "r2_prefix": r2_prefix,
        })

        # ── 6. Mark done (pod NOT terminated — managed by user) ───────
        await training_store.update_training_job(
            job_id,
            status="done",
            completed_at=time.time(),
        )
        logger.info(f"[Orch] Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"[Orch] Job {job_id} failed: {e}")
        await training_store.update_training_job(
            job_id,
            status="failed",
            error=str(e),
            completed_at=time.time(),
        )
