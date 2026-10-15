FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    HOME=/home/appuser \
    PORT=7860 \
    WORK_DIR=/data

# FFmpeg for encoding, MediaInfo for /mediainfo, git for /update, curl for
# the container health check, p7zip (7z) for /leech -e extract and -z zip.
# Megatools powers leech downloads when present.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    mediainfo \
    git \
    curl \
    ca-certificates \
    p7zip-full \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get update && \
    (apt-get install -y --no-install-recommends megatools || \
     echo "megatools unavailable — /leech mega links will not work") && \
    rm -rf /var/lib/apt/lists/*

# UID 1000 matches Hugging Face Spaces' expected runtime user.
RUN useradd --create-home --uid 1000 appuser && \
    mkdir -p /app /data && \
    chown -R appuser:appuser /app /data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

EXPOSE 7860

VOLUME ["/data"]

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["python3", "-m", "bot"]
