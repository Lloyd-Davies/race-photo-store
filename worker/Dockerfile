# Build from repo root:
#   docker build -t photostore-worker:dev -f worker/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install shared package — copy only install metadata first so this layer
# is only invalidated when pyproject.toml changes, not on every .py edit
COPY shared/pyproject.toml ./shared/pyproject.toml
RUN mkdir -p ./shared/photostore && touch ./shared/photostore/__init__.py \
    && pip install --no-cache-dir -e ./shared

# Install worker-specific dependencies
COPY worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy full source (overwrites the placeholder __init__.py)
COPY shared/ ./shared/
COPY worker/ ./

CMD ["sh", "-c", "celery -A tasks worker --loglevel=info --concurrency=${CELERY_CONCURRENCY:-2}"]
