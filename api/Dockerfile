# Build from repo root:
#   docker build -t photostore-api:dev -f api/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install shared package — copy only install metadata first so this layer
# is only invalidated when pyproject.toml changes, not on every .py edit
COPY shared/pyproject.toml ./shared/pyproject.toml
RUN mkdir -p ./shared/photostore && touch ./shared/photostore/__init__.py \
    && pip install --no-cache-dir -e ./shared

# Install API-specific dependencies
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy full source (overwrites the placeholder __init__.py)
COPY shared/ ./shared/
COPY api/ ./

# Run Alembic migrations then start Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}"]
