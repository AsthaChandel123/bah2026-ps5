# Bharat Climate Twin — O(1) serving API (slim Python image).
#
# Build (from the repo root so the data dir is in the build context):
#   docker build -t bct-api -f backend/Dockerfile .
# Run:
#   docker run --rm -p 8000:8000 bct-api
# Then: curl http://localhost:8000/api/health   ·   docs at /docs
#
# The image bakes the precomputed artifacts in at build time. To serve a
# different artifact set, mount it and override BCT_DATA_DIR:
#   docker run --rm -p 8000:8000 -v /path/to/data:/data \
#       -e BCT_DATA_DIR=/data bct-api

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    BCT_DATA_DIR=/app/data/processed/sample

WORKDIR /app

# Install dependencies first for better layer caching.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Application code.
COPY backend/app /app/backend/app

# Precomputed serving artifacts (read into RAM once at startup).
COPY data/processed/sample /app/data/processed/sample

WORKDIR /app/backend

EXPOSE 8000

# Single worker is plenty: all data is in-memory and reads are O(1). Scale
# horizontally (more replicas) behind a load balancer, or move the hot path to
# the Cloudflare Worker in edge/ for true edge serving.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
