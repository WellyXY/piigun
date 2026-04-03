"""
LoRA Training Pod Agent — runs on RunPod pod at port 7860.
Receives commands from the Railway orchestrator and drives ltx-trainer.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from trainer import TrainerState, run_preprocessing, run_training
from r2_sync import download_files, upload_directory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AGENT_SECRET = os.getenv("AGENT_SECRET", "")


def _auth(x_agent_secret: str = Header(default="")):
    if AGENT_SECRET and x_agent_secret != AGENT_SECRET:
        raise HTTPException(status_code=401, detail="Invalid agent secret")


state = TrainerState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[Agent] Pod agent started")
    yield
    logger.info("[Agent] Pod agent shutting down")


app = FastAPI(lifespan=lifespan)


class SetupRequest(BaseModel):
    job_id: str
    r2_video_keys: list[str]
    yaml_config: str
    jsonl_manifest: str
    frames: int = 249


class UploadCheckpointsRequest(BaseModel):
    r2_prefix: str


@app.get("/status")
async def get_status(x_agent_secret: str = Header(default="")):
    _auth(x_agent_secret)
    return {
        "phase": state.phase,
        "current_step": state.current_step,
        "total_steps": state.total_steps,
        "running": state.running,
        "error": state.error,
    }


@app.post("/setup")
async def setup(req: SetupRequest, x_agent_secret: str = Header(default="")):
    _auth(x_agent_secret)
    if state.running:
        raise HTTPException(status_code=409, detail="Training already in progress")

    state.job_id = req.job_id
    state.phase = "downloading"

    # Download videos from R2
    video_dir = f"/workspace/training/{req.job_id}_videos"
    os.makedirs(video_dir, exist_ok=True)
    await asyncio.get_event_loop().run_in_executor(
        None, download_files, req.r2_video_keys, video_dir
    )

    # Write config files
    yaml_path = f"/workspace/training/{req.job_id}.yaml"
    jsonl_path = f"/workspace/training/{req.job_id}.jsonl"
    with open(yaml_path, "w") as f:
        f.write(req.yaml_config)
    with open(jsonl_path, "w") as f:
        f.write(req.jsonl_manifest)

    state.yaml_path = yaml_path
    state.jsonl_path = jsonl_path
    state.frames = req.frames
    state.phase = "ready"

    # Run preprocessing (blocks until done)
    preprocessed_dir = f"/workspace/training/{req.job_id}_preprocessed"
    await asyncio.get_event_loop().run_in_executor(
        None, run_preprocessing, jsonl_path, preprocessed_dir, req.frames, state
    )

    return {"ok": True, "phase": state.phase}


@app.post("/train")
async def start_training(x_agent_secret: str = Header(default="")):
    _auth(x_agent_secret)
    if state.running:
        raise HTTPException(status_code=409, detail="Training already in progress")
    if state.phase not in ("ready", "preprocessing_done"):
        raise HTTPException(status_code=400, detail=f"Not ready to train, phase={state.phase}")

    asyncio.create_task(_run_training_task())
    return {"ok": True, "message": "Training started"}


async def _run_training_task():
    await asyncio.get_event_loop().run_in_executor(
        None, run_training, state.yaml_path, state
    )


@app.get("/logs")
async def stream_logs(x_agent_secret: str = Header(default="")):
    _auth(x_agent_secret)

    log_path = f"/workspace/logs/training_{state.job_id}.log"

    async def generate():
        last_size = 0
        while state.running or state.phase not in ("done", "failed"):
            try:
                if os.path.exists(log_path):
                    with open(log_path) as f:
                        f.seek(last_size)
                        new_content = f.read()
                        if new_content:
                            for line in new_content.splitlines():
                                yield f"{line}\n"
                            last_size = f.tell()
            except Exception:
                pass
            await asyncio.sleep(2)

        # Flush remaining
        if os.path.exists(log_path):
            with open(log_path) as f:
                f.seek(last_size)
                for line in f.read().splitlines():
                    yield f"{line}\n"

    return StreamingResponse(generate(), media_type="text/plain")


@app.get("/checkpoints")
async def list_checkpoints(x_agent_secret: str = Header(default="")):
    _auth(x_agent_secret)
    ckpt_dir = f"/workspace/training/{state.job_id}_output/checkpoints"
    files = []
    if os.path.isdir(ckpt_dir):
        for name in os.listdir(ckpt_dir):
            if name.endswith(".safetensors"):
                path = os.path.join(ckpt_dir, name)
                files.append({
                    "name": name,
                    "size_mb": round(os.path.getsize(path) / 1024 / 1024, 1),
                })
    return {"checkpoints": files}


@app.post("/upload-checkpoints")
async def upload_checkpoints(req: UploadCheckpointsRequest, x_agent_secret: str = Header(default="")):
    _auth(x_agent_secret)
    ckpt_dir = f"/workspace/training/{state.job_id}_output/checkpoints"
    r2_prefix = f"{req.r2_prefix}/checkpoints"
    await asyncio.get_event_loop().run_in_executor(
        None, upload_directory, ckpt_dir, r2_prefix
    )
    return {"ok": True, "uploaded_to": r2_prefix}
