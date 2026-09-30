FROM postgres:16-bookworm AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv age ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY backup/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN mkdir /work && chown postgres:postgres /work /app

FROM dependencies AS runtime
COPY backup/backup.py /app/backup.py
USER postgres
WORKDIR /app
ENTRYPOINT ["python", "/app/backup.py"]
CMD ["schedule"]

FROM dependencies AS tests
RUN pip install --no-cache-dir pytest==8.4.2 'moto[s3,server]==5.1.14' SQLAlchemy==2.0.43 alembic==1.16.5
COPY backup/backup.py /app/backup.py
COPY shared/photostore /app/photostore
COPY api/alembic /app/migrations
COPY backup/tests /app/tests
COPY backup/compose.restore.yml backup/r2-lifecycle.json /app/definitions/
COPY docker-compose.backup.yml /app/definitions/production.yml
USER postgres
WORKDIR /app
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["tests", "-q"]
