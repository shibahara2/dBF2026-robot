FROM --platform=linux/arm64 nvcr.io/nvidia/cuda:13.0.0-cudnn-devel-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libportaudio2 \
        python3.12 \
        python3.12-venv \
    && python3.12 -m venv "$VIRTUAL_ENV" \
    && pip install --no-cache-dir --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-core.txt requirements-voice-gpu.txt ./
RUN pip install --no-cache-dir -r requirements-core.txt \
    && pip install --no-cache-dir -r requirements-voice-gpu.txt

COPY app ./app
COPY voice_ui ./voice_ui

CMD ["python", "-m", "voice_ui.main"]
