#!/bin/bash
# Worker launcher — uses venv python so deps (redis/pydantic/asyncpg/boto3/httpx/pillow/tenacity)
# persist across fresh pods via the network-volume-mounted /workspace/venv.
# Previously used system python3, which required re-pip-installing on every new pod.

set -a
source /workspace/parrot-service/.env
set +a

# LD_LIBRARY_PATH for nvidia CUDA libs (torch dynamic loading)
NVCU12=/usr/local/lib/python3.11/dist-packages/nvidia
for d in nvjitlink cusparse cusparselt cublas cudnn cufft curand cusolver cuda_runtime; do
    [ -d "${NVCU12}/${d}/lib" ] && export LD_LIBRARY_PATH="${NVCU12}/${d}/lib:${LD_LIBRARY_PATH:-}"
done

cd /workspace/parrot-service
exec /workspace/venv/bin/python -m workers.gpu_worker --gpu_id 0
