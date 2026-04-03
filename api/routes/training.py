"""
Training management routes — admin only.
Handles job creation, status, log streaming, checkpoint deploy.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

import boto3
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from api.auth import require_admin
from api.config import settings
from api.models import (
    CreateTrainingJobRequest,
    TrainingCheckpoint,
    TrainingJobDetailResponse,
    TrainingJobResponse,
)
from db import training_store
from training import runpod_client
from training.config_generator import build_jsonl_manifest, build_yaml_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/training", dependencies=[Depends(require_admin)])


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def _job_to_response(job: dict) -> TrainingJobResponse:
    return TrainingJobResponse(
        id=job["id"],
        position=job["position"],
        status=job["status"],
        pod_id=job.get("pod_id"),
        pod_ip=job.get("pod_ip"),
        r2_prefix=job["r2_prefix"],
        config=job["config"] if isinstance(job["config"], dict) else json.loads(job["config"]),
        current_step=job["current_step"],
        total_steps=job["total_steps"],
        error=job.get("error"),
        created_at=float(job["created_at"]),
        completed_at=float(job["completed_at"]) if job.get("completed_at") else None,
    )


@router.post("/jobs/prepare")
async def prepare_training_job():
    """Reserve a job_id so the client can upload videos before creating the job."""
    job_id = str(uuid.uuid4())
    return {"job_id": job_id}


@router.post("/jobs/upload-video")
async def upload_training_video(
    job_id: str = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Upload a training video to R2 before creating the job.
    Returns the R2 key for the uploaded video.
    """
    key = f"training/{job_id}/videos/{filename}"
    content = await file.read()
    client = _r2_client()
    client.put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType="video/mp4",
    )
    return {"key": key, "job_id": job_id, "filename": filename}


@router.post("/jobs", response_model=TrainingJobResponse)
async def create_training_job(req: CreateTrainingJobRequest):
    """
    Create a training job. Videos must already be uploaded to R2 at
    training/{job_id}/videos/{filename} before calling this endpoint.
    This endpoint provisions the RunPod pod and kicks off the orchestrator.
    """
    job_id = req.job_id if req.job_id else str(uuid.uuid4())
    r2_prefix = f"training/{job_id}"

    config = {
        "steps": req.steps,
        "learning_rate": req.learning_rate,
        "rank": req.rank,
        "frames": req.frames,
        "pod_url": req.pod_url.rstrip("/"),
        "validation_prompt": req.validation_prompt,
        "videos": [{"filename": v.filename, "caption": v.caption} for v in req.videos],
    }

    job = await training_store.create_training_job_with_id(
        job_id=job_id,
        position=req.position,
        r2_prefix=r2_prefix,
        config=config,
    )

    # Launch pod provisioning in background
    from training.orchestrator import start_job_orchestration
    asyncio.create_task(start_job_orchestration(job["id"]))

    return _job_to_response(job)


@router.get("/jobs", response_model=list[TrainingJobResponse])
async def list_training_jobs():
    jobs = await training_store.list_training_jobs()
    return [_job_to_response(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=TrainingJobDetailResponse)
async def get_training_job(job_id: str):
    job = await training_store.get_training_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    base = _job_to_response(job)
    checkpoints = _list_checkpoints(job["r2_prefix"])

    return TrainingJobDetailResponse(
        **base.model_dump(),
        checkpoints=checkpoints,
    )


def _list_checkpoints(r2_prefix: str) -> list[TrainingCheckpoint]:
    """List checkpoint .safetensors files in R2 under {r2_prefix}/checkpoints/"""
    try:
        client = _r2_client()
        prefix = f"{r2_prefix}/checkpoints/"
        resp = client.list_objects_v2(Bucket=settings.R2_BUCKET_NAME, Prefix=prefix)
        items = []
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            name = key.split("/")[-1]
            if not name.endswith(".safetensors"):
                continue
            step = 0
            try:
                step = int(name.replace("lora_weights_step_", "").replace(".safetensors", ""))
            except ValueError:
                pass
            items.append(TrainingCheckpoint(
                key=key,
                name=name,
                size_mb=round(obj["Size"] / 1024 / 1024, 1),
                step=step,
            ))
        return sorted(items, key=lambda x: x.step)
    except Exception as e:
        logger.warning(f"Failed to list checkpoints for {r2_prefix}: {e}")
        return []


@router.get("/jobs/{job_id}/logs")
async def stream_job_logs(job_id: str):
    """
    SSE stream of training logs proxied from pod agent.
    """
    job = await training_store.get_training_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    async def generate():
        import httpx

        pod_ip = job.get("pod_ip")
        if not pod_ip:
            yield f"data: No pod assigned yet. Status: {job['status']}\n\n"
            return

        agent_url = f"{pod_ip}/logs"

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "GET", agent_url,
                    headers={"X-Agent-Secret": settings.AGENT_SECRET},
                    timeout=300,
                ) as resp:
                    async for line in resp.aiter_lines():
                        yield f"data: {line}\n\n"
        except Exception as e:
            yield f"data: [Connection to pod lost: {e}]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/jobs/{job_id}/deploy/{checkpoint_name}")
async def deploy_checkpoint(job_id: str, checkpoint_name: str):
    """
    Copy a checkpoint from training R2 path to the production loras/ path.
    """
    job = await training_store.get_training_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    src_key = f"{job['r2_prefix']}/checkpoints/{checkpoint_name}"
    dst_key = f"loras/{job['position']}.safetensors"

    client = _r2_client()
    try:
        client.copy_object(
            Bucket=settings.R2_BUCKET_NAME,
            CopySource={"Bucket": settings.R2_BUCKET_NAME, "Key": src_key},
            Key=dst_key,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"R2 copy failed: {e}")

    return {
        "ok": True,
        "deployed": dst_key,
        "position": job["position"],
        "checkpoint": checkpoint_name,
        "note": "Restart the inference server to load the new LoRA.",
    }


@router.delete("/jobs/{job_id}")
async def cancel_training_job(job_id: str):
    """Terminate the RunPod pod and mark job as cancelled."""
    job = await training_store.get_training_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")

    pod_id = job.get("pod_id")
    if pod_id:
        try:
            await runpod_client.terminate_pod(pod_id)
        except Exception as e:
            logger.warning(f"Pod termination failed: {e}")

    await training_store.update_training_job(
        job_id,
        status="cancelled",
        completed_at=time.time(),
        error="Cancelled by admin",
    )
    return {"ok": True, "job_id": job_id}
