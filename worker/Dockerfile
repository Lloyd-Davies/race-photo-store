# Build from repo root:
#   docker build -t photostore-worker:dev -f worker/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install shared package first — good layer cache separation
COPY shared/ ./shared/
RUN pip install --no-cache-dir -e ./shared

# Install worker-specific dependencies
COPY worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker source
COPY worker/ ./

CMD ["sh", "-c", "celery -A tasks worker --loglevel=info --concurrency=${CELERY_CONCURRENCY:-2}"]
