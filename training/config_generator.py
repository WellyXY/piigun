"""
Generates ltx-trainer YAML config and JSONL dataset manifest
from a TrainingJob config dict.
"""
from __future__ import annotations

import json
from typing import Optional

import yaml


LTX_MODEL_PATH = "/workspace/models/ltx23/ltx-2.3-22b-distilled.safetensors"
TEXT_ENCODER_PATH = "/workspace/gemma_configs"


def build_yaml_config(job_id: str, position: str, config: dict) -> str:
    """
    Build ltx-trainer YAML config string from job parameters.

    config keys (all optional, defaults shown):
        steps: 2000
        learning_rate: 0.0001
        rank: 32
        frames: 249
        validation_prompt: str  (auto-generated if missing)
    """
    steps = int(config.get("steps", 2000))
    lr = float(config.get("learning_rate", 1e-4))
    rank = int(config.get("rank", 32))
    frames = int(config.get("frames", 249))
    val_prompt = config.get(
        "validation_prompt",
        f"A person performing {position} motion. --{position}"
    )

    data = {
        "model": {
            "model_path": LTX_MODEL_PATH,
            "text_encoder_path": TEXT_ENCODER_PATH,
            "training_mode": "lora",
            "load_checkpoint": None,
        },
        "lora": {
            "rank": rank,
            "alpha": rank,
            "dropout": 0.0,
            "target_modules": ["to_k", "to_q", "to_v", "to_out.0"],
        },
        "training_strategy": {
            "name": "text_to_video",
            "first_frame_conditioning_p": 0.9,
            "with_audio": False,
        },
        "optimization": {
            "learning_rate": lr,
            "steps": steps,
            "batch_size": 1,
            "gradient_accumulation_steps": 1,
            "max_grad_norm": 1.0,
            "optimizer_type": "adamw8bit",
            "scheduler_type": "linear",
            "enable_gradient_checkpointing": True,
        },
        "acceleration": {
            "mixed_precision_mode": "bf16",
            "quantization": "int8-quanto",
            "load_text_encoder_in_8bit": True,
        },
        "data": {
            "preprocessed_data_root": f"/workspace/training/{job_id}_preprocessed",
            "num_dataloader_workers": 2,
        },
        "validation": {
            "prompts": [val_prompt],
            "negative_prompt": "worst quality, inconsistent motion, blurry, jittery, distorted",
            "images": None,
            "video_dims": [512, 768, frames],
            "frame_rate": 25.0,
            "seed": 42,
            "inference_steps": 30,
            "interval": 500,
            "videos_per_prompt": 1,
            "guidance_scale": 4.0,
            "stg_scale": 1.0,
            "stg_blocks": [29],
            "stg_mode": "stg_v",
            "generate_audio": False,
            "skip_initial_validation": True,
        },
        "checkpoints": {
            "interval": 500,
            "keep_last_n": 4,
            "precision": "bfloat16",
        },
        "seed": 42,
        "output_dir": f"/workspace/training/{job_id}_output",
    }
    return yaml.dump(data, default_flow_style=False, allow_unicode=True)


def build_jsonl_manifest(videos: list[dict]) -> str:
    """
    Build JSONL dataset manifest.
    videos: list of {"path": "/workspace/training/{job_id}_videos/foo.mp4", "caption": "..."}
    Returns newline-separated JSON lines.
    """
    lines = []
    for v in videos:
        lines.append(json.dumps({"media_path": v["path"], "caption": v["caption"]}))
    return "\n".join(lines)
