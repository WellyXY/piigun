#!/bin/bash
set -e

mkdir -p /workspace/logs /workspace/training

echo "[start.sh] Starting pod agent on port 7860"
cd /agent
uvicorn main:app --host 0.0.0.0 --port 7860 --workers 1
