"""
Cloudflare R2 video upload.
Uses boto3 with R2's S3-compatible endpoint.
"""
from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError

from api.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.R2_ACCOUNT_ID:
            raise RuntimeError("R2_ACCOUNT_ID is not set")
        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
    return _client


def upload_video(job_id: str, local_path: str) -> str:
    """
    Upload a video file to R2.
    Returns the public URL.
    Raises on failure.
    """
    key = f"videos/{job_id}.mp4"
    client = _get_client()

    logger.info(f"[R2] Uploading {local_path} → {settings.R2_BUCKET_NAME}/{key}")
    client.upload_file(
        local_path,
        settings.R2_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    public_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"
    logger.info(f"[R2] Upload complete: {public_url}")
    return public_url


def upload_image(image_id: str, local_path: str) -> str:
    """Upload an input image to R2. Returns the public URL."""
    key = f"uploads/{image_id}.jpg"
    client = _get_client()
    logger.info(f"[R2] Uploading image {local_path} → {key}")
    client.upload_file(
        local_path,
        settings.R2_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": "image/jpeg"},
    )
    public_url = f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"
    logger.info(f"[R2] Image upload complete: {public_url}")
    return public_url


def delete_video(job_id: str):
    """Delete a video from R2 (e.g. during cleanup)."""
    key = f"videos/{job_id}.mp4"
    try:
        _get_client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        logger.info(f"[R2] Deleted {key}")
    except ClientError as e:
        logger.warning(f"[R2] Delete failed for {key}: {e}")
