FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

# System deps
RUN apt-get update && apt-get install -y git ffmpeg && rm -rf /var/lib/apt/lists/*

# Install ltx-trainer
RUN git clone https://github.com/Lightricks/LTX-Video-Trainer.git /workspace/ltx-trainer && \
    cd /workspace/ltx-trainer && \
    pip install --no-cache-dir -e .

# Install pod agent
COPY requirements.txt /agent/requirements.txt
RUN pip install --no-cache-dir -r /agent/requirements.txt

COPY main.py /agent/main.py
COPY trainer.py /agent/trainer.py
COPY r2_sync.py /agent/r2_sync.py

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 7860
CMD ["/start.sh"]
