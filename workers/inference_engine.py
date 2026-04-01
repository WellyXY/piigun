"""
Inference engine: HTTP client that calls the local LTX server (server.py on RunPod).
The server already has the model loaded in VRAM — no need to reload here.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

INFERENCE_SERVER_URL = os.getenv("INFERENCE_SERVER_URL", "http://localhost:8000")


@dataclass
class InferenceEngine:
    gpu_id: int
    model_path: str = ""
    lora_dir: str = ""
    fast_lora_dir: str = ""
    server_url: str = field(default_factory=lambda: INFERENCE_SERVER_URL)

    def startup(self):
        """Verify the local inference server is reachable."""
        for attempt in range(10):
            try:
                resp = httpx.get(f"{self.server_url}/status", timeout=10)
                resp.raise_for_status()
                status = resp.json()
                logger.info(f"[GPU {self.gpu_id}] Inference server ready: {status.get('status')}")
                return
            except Exception as e:
                logger.warning(f"[GPU {self.gpu_id}] Server not ready (attempt {attempt + 1}): {e}")
                time.sleep(5)
        raise RuntimeError(f"Inference server at {self.server_url} not reachable after 10 attempts")

    def generate(
        self,
        *,
        position: str,
        image_path: str,
        prompt: str = "",
        duration: int = 10,
        seed: int = 42,
        **kwargs,
    ) -> tuple[str, float]:
        """
        Call the local server to generate a video.
        Returns (output_path, generation_time_seconds).
        """
        num_frames = 161 if duration >= 10 else 81

        t0 = time.time()
        logger.info(f"[GPU {self.gpu_id}] Calling server: position={position}, frames={num_frames}")

        resp = httpx.post(
            f"{self.server_url}/generate",
            json={
                "prompt": prompt,
                "position": position,
                "image_path": image_path,
                "num_frames": num_frames,
                "seed": seed,
                "enhance": True,
            },
            timeout=600,
        )
        resp.raise_for_status()
        result = resp.json()
        gen_time = time.time() - t0

        # Prefer enhanced video (GFPGAN), fall back to raw
        video_path = result.get("enhanced_video") or result["raw_video"]
        logger.info(f"[GPU {self.gpu_id}] Server returned: {video_path} in {gen_time:.1f}s")

        return video_path, result.get("inference_s", gen_time)
