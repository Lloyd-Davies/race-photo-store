# race-photo-store

Self-hosted sports event photo proofing and sales platform. Athletes browse public watermarked proofs, select photos, pay via Stripe, and receive a ZIP of full-resolution originals.

## Stack

| Service | Technology |
|---|---|
| API | FastAPI + SQLAlchemy + Alembic |
| Worker | Celery |
| Database | PostgreSQL 16 |
| Broker/Cache | Redis 7 |
| Reverse proxy | Nginx |
| Infrastructure | Oracle Cloud ARM64 VM, Portainer, Cloudflare Tunnel |

## Repo structure

```
shared/          # Python package installed into both api + worker images
  photostore/
    config.py    # pydantic-settings — all env vars
    models.py    # SQLAlchemy ORM models
    db.py        # Engine + session factory
    celery_app.py

api/
  app/
    main.py      # FastAPI app
    routes/      # One file per route group
    schemas.py   # Pydantic request/response models
    deps.py
  alembic/       # DB migrations (run automatically on container start)
  Dockerfile

worker/
  tasks/
    build_zip.py    # build_zip(order_id)
    archive.py      # archive_event / restore_event
  Dockerfile

nginx/
  nginx.conf

docker-compose.yml
.env.example
```

## Local setup

```bash
cp .env.example .env
# Fill in POSTGRES_PASSWORD, STRIPE_*, PUBLIC_BASE_URL, ADMIN_TOKEN

docker build -t photostore-api:dev -f api/Dockerfile .
docker build -t photostore-worker:dev -f worker/Dockerfile .
docker compose up -d
```

> The nginx config is bind-mounted from the host at `/opt/photostore/nginx/nginx.conf`.  
> Create this directory and copy `nginx/nginx.conf` there before starting the stack.

## Environment variables

| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `STRIPE_SECRET_KEY` | Stripe secret key (`sk_test_...`) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `STRIPE_PRICE_ID` | Stripe Price ID for a single photo |
| `PUBLIC_BASE_URL` | Public URL, e.g. `https://photos.example.com` |
| `ADMIN_TOKEN` | Bearer token for admin endpoints |

## End-to-end test (curl)

See `context.md` for the full manual test script.

1. Place proof + original files under `/mnt/pstore/photos/`
2. `POST /api/admin/events` — create event
3. `POST /api/admin/events/{id}/ingest` — scan proofs directory
4. `POST /api/carts` — select photos
5. `POST /api/checkout` — get Stripe Checkout URL
6. Complete payment in Stripe test mode
7. Poll `GET /api/orders/{id}` until `READY`
8. `GET /d/{token}` — download ZIP
