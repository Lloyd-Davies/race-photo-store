# race-photo-store

Minimal self-hosted race photo platform.

Athletes browse proofs, checkout with Stripe, and download originals as ZIPs.

## At a glance

| Layer | Stack |
|---|---|
| API | FastAPI + SQLAlchemy + Alembic |
| Worker | Celery |
| Data | PostgreSQL 16 + Redis 7 |
| Edge | Nginx + Cloudflare Tunnel |
| Frontend | React + Vite + Tailwind |

## Network requirement (current)

The current production compose setup expects **Cloudflare Tunnel** for public ingress.

Traffic path:

`Internet -> Cloudflare -> cloudflared -> nginx -> api/frontend`

Notes:

- `docker-compose.yml` binds nginx to `127.0.0.1:8081`, so external traffic is intended to come through Cloudflare Tunnel.
- `CLOUDFLARE_TUNNEL_TOKEN` is required for current production exposure.
- Local dev can run without tunnel (see `docker-compose.local.yml`, where `cloudflared` is disabled by profile).

## Quick start (local)

1) Create env file:

```bash
cp .env.example .env
```

2) Start stack:

```bash
docker compose up -d --build
```

3) Health check:

```bash
curl http://localhost:8081/api/health
```

## Production (current compose)

1) Prepare host dirs:

```bash
sudo mkdir -p /mnt/pstore/{pgdata,redis,photos}
sudo chown -R $USER:$USER /mnt/pstore
```

2) Set required env:

- `POSTGRES_PASSWORD`
- `PUBLIC_BASE_URL`
- `ADMIN_TOKEN`
- `CLOUDFLARE_TUNNEL_TOKEN`

3) Optional but recommended:

- `ADMIN_SESSION_SECRET`
- Stripe vars (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`)

4) Deploy `docker-compose.yml` (Portainer or Docker), then verify:

- `GET /api/health` returns healthy
- admin login works
- gallery, checkout, and download flow work end-to-end

## Security model

- Admin uses login + signed short-lived session tokens (`/api/admin/login`, `/api/admin/refresh`).
- Event locking is **per-event** and configured at event creation/edit (hashed secret storage).
- Order status access is signed-token protected (prevents order ID enumeration).
- Proof and ZIP delivery are gated via API checks + nginx internal locations.
- Sensitive endpoints are rate-limited (API and nginx edge controls).
- Admin upload path enforces a max upload size.

## Core API

Public:

- `GET /api/events`
- `GET /api/events/{id}/photos`
- `POST /api/events/{id}/unlock`

Checkout and delivery:

- `POST /api/carts`
- `POST /api/checkout`
- `GET /api/orders/{id}`
- `GET /d/{token}`

Admin:

- `POST /api/admin/login`
- `POST /api/admin/refresh`
- `POST /api/admin/events`
- `PATCH /api/admin/events/{id}`
- `POST /api/admin/events/{id}/ingest`
- `POST /api/admin/events/{id}/tags/bibs`
- `GET /api/admin/orders`

## Configuration

Primary env vars:

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `PUBLIC_BASE_URL` | Public URL used in generated links |
| `ADMIN_TOKEN` | Base admin credential for login |
| `ADMIN_SESSION_SECRET` | Signing key for admin/event/order access tokens |
| `CLOUDFLARE_TUNNEL_TOKEN` | Cloudflare tunnel connector token |

Security tuning:

| Variable | Default |
|---|---|
| `ADMIN_SESSION_TTL_MINUTES` | `30` |
| `ADMIN_REFRESH_TTL_HOURS` | `12` |
| `EVENT_ACCESS_TTL_HOURS` | `12` |
| `ORDER_ACCESS_TTL_HOURS` | `720` |
| `MAX_PHOTO_UPLOAD_BYTES` | `26214400` |

## Validation

```bash
python -m pytest api/tests -q
python -m pytest worker/tests -q
npm --prefix frontend run build
```

## Repo layout

```text
api/                FastAPI application
worker/             Celery tasks
frontend/           React app
shared/photostore/  Shared models/config/db
nginx/              Nginx config and image
```
