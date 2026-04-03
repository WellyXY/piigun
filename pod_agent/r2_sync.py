"""
R2 upload/download helpers for the pod agent.
Uses boto3 with env vars R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import boto3

logger = logging.getLogger(__name__)


def _client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def download_files(r2_keys: list[str], local_dir: str) -> None:
    """Download a list of R2 keys into local_dir, preserving filename."""
    client = _client()
    bucket = os.environ["R2_BUCKET_NAME"]
    Path(local_dir).mkdir(parents=True, exist_ok=True)
    for key in r2_keys:
        filename = key.split("/")[-1]
        dest = os.path.join(local_dir, filename)
        logger.info(f"[R2] Downloading {key} → {dest}")
        client.download_file(bucket, key, dest)


def upload_directory(local_dir: str, r2_prefix: str) -> None:
    """Upload all files in local_dir to R2 under r2_prefix/filename."""
    client = _client()
    bucket = os.environ["R2_BUCKET_NAME"]
    for name in os.listdir(local_dir):
        local_path = os.path.join(local_dir, name)
        if not os.path.isfile(local_path):
            continue
        key = f"{r2_prefix}/{name}"
        logger.info(f"[R2] Uploading {local_path} → {key}")
        client.upload_file(local_path, bucket, key)
