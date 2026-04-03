"""
RunPod REST API v1 client.
Docs: https://rest.runpod.io/v1
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from api.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://rest.runpod.io/v1"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.RUNPOD_API_KEY}"}


async def create_pod(
    job_id: str,
    gpu_type_id: str,
    extra_env: Optional[dict] = None,
) -> dict:
    """
    Create an on-demand RunPod pod and return the full pod dict.
    The pod will run racoonn/lora-trainer-agent:latest and expose port 7860/http.
    extra_env: additional env vars merged with R2 creds and AGENT_SECRET.
    """
    env = {
        "AGENT_SECRET": settings.AGENT_SECRET,
        "R2_ACCOUNT_ID": settings.R2_ACCOUNT_ID,
        "R2_ACCESS_KEY_ID": settings.R2_ACCESS_KEY_ID,
        "R2_SECRET_ACCESS_KEY": settings.R2_SECRET_ACCESS_KEY,
        "R2_BUCKET_NAME": settings.R2_BUCKET_NAME,
        "R2_PUBLIC_URL": settings.R2_PUBLIC_URL,
        "JOB_ID": job_id,
    }
    if extra_env:
        env.update(extra_env)

    payload = {
        "name": f"lora-{job_id[:8]}",
        "imageName": settings.RUNPOD_IMAGE_NAME,
        "gpuTypeId": gpu_type_id,
        "containerDiskInGb": settings.RUNPOD_CONTAINER_DISK_GB,
        "ports": f"{settings.AGENT_PORT}/http",
        "env": env,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{_BASE}/pods", json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[RunPod] Created pod: {data.get('id')}")
        return data


async def get_pod(pod_id: str) -> dict:
    """Return pod status dict. Key fields: id, status, runtime.ports"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{_BASE}/pods/{pod_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def terminate_pod(pod_id: str) -> None:
    """Terminate (delete) a pod immediately."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.delete(f"{_BASE}/pods/{pod_id}", headers=_headers())
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
        logger.info(f"[RunPod] Terminated pod: {pod_id}")


def get_pod_public_url(pod: dict) -> Optional[str]:
    """
    Extract the public HTTP URL for port 7860 from a pod status dict.
    RunPod public URL format: https://{pod_id}-{port}.proxy.runpod.net
    """
    pod_id = pod.get("id", "")
    # Check runtime.ports array
    runtime = pod.get("runtime") or {}
    ports = runtime.get("ports") or []
    for p in ports:
        if p.get("privatePort") == settings.AGENT_PORT and p.get("type") == "http":
            public_port = p.get("publicPort")
            if public_port:
                return f"https://{pod_id}-{public_port}.proxy.runpod.net"
    # Fallback: construct standard URL
    if pod_id and pod.get("status") == "RUNNING":
        return f"https://{pod_id}-{settings.AGENT_PORT}.proxy.runpod.net"
    return None
