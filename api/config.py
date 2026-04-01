import os
from pathlib import Path


class Settings:
    PROJECT_NAME: str = "Parrot Video API"
    API_VERSION: str = "v1"

    # ── Redis (Railway plugin / RunPod public URL) ──
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── PostgreSQL (Railway plugin) ──
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # ── Cloudflare R2 ──
    R2_ACCOUNT_ID: str = os.getenv("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID: str = os.getenv("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY: str = os.getenv("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME: str = os.getenv("R2_BUCKET_NAME", "parrot-videos")
    R2_PUBLIC_URL: str = os.getenv("R2_PUBLIC_URL", "")  # https://pub-xxx.r2.dev

    # ── API ──
    VIDEO_BASE_URL: str = os.getenv("VIDEO_BASE_URL", "http://localhost:8000/v1/jobs")
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "parrot-webhook-secret")
    NUM_GPUS: int = int(os.getenv("NUM_GPUS", "1"))

    # ── RunPod model paths (used only by worker) ──
    BASE_MODEL_PATH: str = os.getenv("BASE_MODEL_PATH", "/raid/training/ai-toolkit/models/Wan2.2-I2V-A14B-Diffusers")
    LORA_DIR: str = os.getenv("LORA_DIR", "/raid/training/ai-toolkit/output_10s_conv")
    FAST_LORA_DIR: str = os.getenv("FAST_LORA_DIR", "/raid/training/ai-toolkit/models/fast_loras")
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", "/tmp/videos")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/tmp/uploads")

    # ── Job settings ──
    JOB_TTL_HOURS: int = int(os.getenv("JOB_TTL_HOURS", "168"))  # 7 days in Redis
    QUEUE_EXPIRE_SECONDS: int = int(os.getenv("QUEUE_EXPIRE_SECONDS", "300"))

    # ── Post-processing (worker only) ──
    POSTPROCESS_ENABLED: bool = os.getenv("POSTPROCESS_ENABLED", "true").lower() == "true"
    RIFE_DIR: str = os.getenv("RIFE_DIR", "/raid/training/ai-toolkit/Practical-RIFE")
    UPSCALE_FACTOR: int = 2
    TARGET_FPS: int = 30
    OUTPUT_FPS: int = 30
    OUTPUT_RESOLUTION: str = "720p"

    # ── Video defaults ──
    DEFAULT_NUM_FRAMES: int = 161
    DEFAULT_HEIGHT: int = 768
    DEFAULT_WIDTH: int = 512
    DEFAULT_FPS: int = 16


settings = Settings()

Path(settings.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
