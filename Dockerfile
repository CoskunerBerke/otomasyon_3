# =====================================================================
# REELS AI FACTORY — CLOUD CONTROL PLANE DOCKERFILE (RAILWAY PRODUCTION)
# =====================================================================
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install production python dependencies for cloud control plane
RUN pip install --no-cache-dir \
    requests \
    tzdata \
    pyyaml \
    "boto3>=1.34.0" \
    "psycopg[binary]>=3.1.0"

# Copy application codebase
COPY . .

# Environment settings
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production
ENV APP_TIMEZONE=Europe/Istanbul

# Railway dynamically injects PORT environment variable at runtime
EXPOSE 8000

# Start Cloud Control Plane Server binding to dynamic $PORT
CMD ["sh", "-c", "python -m automation.cloud.app --port ${PORT:-8000} --host 0.0.0.0"]
