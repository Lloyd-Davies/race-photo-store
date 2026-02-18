# Build from repo root:
#   docker build -t photostore-api:dev -f api/Dockerfile .

FROM python:3.12-slim

WORKDIR /app

# Install shared package first — good layer cache separation
COPY shared/ ./shared/
RUN pip install --no-cache-dir -e ./shared

# Install API-specific dependencies
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy API source
COPY api/ ./

# Run Alembic migrations then start Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-2}"]
