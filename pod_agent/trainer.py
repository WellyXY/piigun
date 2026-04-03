"""
Wraps ltx-trainer subprocess calls (process_dataset.py and train.py).
Uses a shared TrainerState object to track progress.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

LTX_TRAINER_DIR = os.getenv("LTX_TRAINER_DIR", "/workspace/ltx-trainer")
LOG_DIR = "/workspace/logs"


@dataclass
class TrainerState:
    job_id: str = ""
    phase: str = "idle"          # idle | downloading | preprocessing | training | uploading | done | failed
    current_step: int = 0
    total_steps: int = 2000
    running: bool = False
    error: Optional[str] = None
    yaml_path: Optional[str] = None
    jsonl_path: Optional[str] = None
    frames: int = 249


def run_preprocessing(jsonl_path: str, preprocessed_dir: str, frames: int, state: TrainerState) -> None:
    """
    Run ltx-trainer's process_dataset.py to preprocess latents + captions.
    Blocks until complete.
    """
    os.makedirs(preprocessed_dir, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = f"{LOG_DIR}/training_{state.job_id}.log"

    state.phase = "preprocessing"
    state.running = True

    cmd = [
        "python3",
        os.path.join(LTX_TRAINER_DIR, "scripts", "process_dataset.py"),
        jsonl_path,
        "--resolution-buckets", f"512x768x{frames}",
        "--output-dir", preprocessed_dir,
    ]
    logger.info(f"[Trainer] Preprocessing: {' '.join(cmd)}")

    with open(log_path, "a") as log_file:
        log_file.write("=== Preprocessing ===\n")
        result = subprocess.run(
            cmd,
            cwd=LTX_TRAINER_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    if result.returncode != 0:
        state.phase = "failed"
        state.running = False
        state.error = f"Preprocessing failed with exit code {result.returncode}"
        raise RuntimeError(state.error)

    state.phase = "preprocessing_done"


def run_training(yaml_path: str, state: TrainerState) -> None:
    """
    Run ltx-trainer's train.py with the given YAML config.
    Parses stdout for step progress. Blocks until complete.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = f"{LOG_DIR}/training_{state.job_id}.log"

    state.phase = "training"
    state.running = True

    cmd = [
        "python3",
        os.path.join(LTX_TRAINER_DIR, "train.py"),
        yaml_path,
    ]
    logger.info(f"[Trainer] Training: {' '.join(cmd)}")

    step_re = re.compile(r"Step[:\s]+(\d+)/(\d+)")

    with open(log_path, "a") as log_file:
        log_file.write("=== Training ===\n")
        proc = subprocess.Popen(
            cmd,
            cwd=LTX_TRAINER_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in proc.stdout:
            log_file.write(line)
            log_file.flush()
            m = step_re.search(line)
            if m:
                state.current_step = int(m.group(1))
                state.total_steps = int(m.group(2))

        proc.wait()

    if proc.returncode != 0:
        state.phase = "failed"
        state.running = False
        state.error = f"Training failed with exit code {proc.returncode}"
        raise RuntimeError(state.error)

    state.phase = "done"
    state.running = False
    logger.info(f"[Trainer] Training complete for job {state.job_id}")
