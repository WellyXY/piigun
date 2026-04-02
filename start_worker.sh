#!/bin/bash
export LD_LIBRARY_PATH=/usr/local/lib/python3.11/dist-packages/nvidia/cu13/lib:$LD_LIBRARY_PATH
cd /workspace/parrot-service
exec python3 -m workers.gpu_worker --gpu_id 0
