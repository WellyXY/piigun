from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


AVAILABLE_POSITIONS = [
    "blow_job", "cowgirl", "doggy",
    "masturbation", "missionary", "reverse_cowgirl",
]


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Request models ──────────────────────────────────────────────

class GenerateRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    position: str = "cowgirl"
    prompt: Optional[str] = ""
    duration: int = Field(default=10, ge=5, le=10)
    seed: Optional[int] = None
    callback_url: Optional[str] = None
    include_audio: bool = False
    audio_description: Optional[str] = ""

    @model_validator(mode="after")
    def check_image_source(self):
        if not self.image_url and not self.image_base64:
            raise ValueError("Either image_url or image_base64 must be provided")
        if self.position not in AVAILABLE_POSITIONS:
            raise ValueError(
                f"Invalid position '{self.position}'. "
                f"Available: {', '.join(AVAILABLE_POSITIONS)}"
            )
        return self


# ── Response models ─────────────────────────────────────────────

class GenerateResponse(BaseModel):
    job_id: str
    status: JobStatus
    position_in_queue: int
    estimated_wait_seconds: int


class JobMetadata(BaseModel):
    position: str
    duration: int
    resolution: str = "720p"
    fps: int = 30
    prompt: str = ""


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = 0.0
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None
    metadata: JobMetadata


class PositionInfo(BaseModel):
    name: str
    description: str = ""


class PositionsResponse(BaseModel):
    positions: list[PositionInfo]


class UsageResponse(BaseModel):
    api_key: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    month: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class WebhookPayload(BaseModel):
    event: str
    job_id: str
    video_url: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[JobMetadata] = None


# ── Credits ──────────────────────────────────────────────────────

class InsufficientCreditsResponse(BaseModel):
    error: str = "Insufficient credits"
    required: float
    available: float


class AccountUsageResponse(BaseModel):
    api_key: str
    credits: float
    credits_used: float
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    month: str


class AccountJobItem(BaseModel):
    job_id: str
    position: str
    duration: int
    status: str
    credits_charged: float
    video_url: Optional[str] = None
    created_at: float
    completed_at: Optional[float] = None
    prompt: str
    seed: int
    callback_url: str


class AccountJobsResponse(BaseModel):
    jobs: list[AccountJobItem]
    total: int
    page: int
    limit: int


# ── Admin ─────────────────────────────────────────────────────────

class AdminKeyItem(BaseModel):
    key_hash: str
    name: str
    created_at: float
    disabled: bool
    credits: float
    credits_used: float
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    raw_key: str = ""


class AdminJobItem(BaseModel):
    job_id: str
    key_name: Optional[str] = None
    api_key_hash: str
    position: str
    duration: int
    status: str
    credits_charged: float
    video_url: Optional[str] = None
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    runtime_seconds: Optional[float] = None
    prompt: str
    seed: int
    callback_url: str


class AdminJobsResponse(BaseModel):
    jobs: list[AdminJobItem]
    total: int
    page: int
    limit: int


class CreateKeyRequest(BaseModel):
    name: str
    credits: float = 0.0


class TopUpRequest(BaseModel):
    add_credits: float


class DisableKeyRequest(BaseModel):
    disabled: bool
