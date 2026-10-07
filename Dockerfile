FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Fonts for the burned-in captions (the app falls back to DejaVu on Linux).
# ffmpeg itself ships inside the imageio-ffmpeg wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY assets ./assets

# Persistent storage (mount a Railway volume here): uploads, rendered videos, thumbnails.
RUN mkdir -p /app/data /app/input_videos /app/assets/music

# Railway injects $PORT. One worker only: the render queue lives in memory.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
