# race-photo-store

Self-hosted sports event photo proofing and sales platform.

Athletes browse public watermarked proofs, select images, pay via Stripe Checkout, and download a ZIP of full-resolution originals.

## Architecture

| Service | Technology |
|---|---|
| API | FastAPI + SQLAlchemy + Alembic |
| Worker | Celery |
| Database | PostgreSQL 16 |
| Broker/Cache | Redis 7 |
| Reverse proxy | Nginx |
| Frontend | React + Vite + Tailwind |
| Deployment | Docker Compose + Portainer + Cloudflare Tunnel |

## Key capabilities

- Public event gallery with proof image browsing
- Bib search and time-of-day filtering (`start_time`, `end_time`)
- Fullscreen proof viewer from gallery cards
- Stripe Checkout order flow
- Async ZIP generation in worker
- Tokenized download links served through nginx `X-Accel-Redirect`
- Admin event ingest + bib tagging
- Admin order management and delivery reset tools

## Repository layout

```text
api/                # FastAPI application
frontend/           # React/Vite frontend
worker/             # Celery tasks (ZIP build etc.)
shared/photostore/  # shared models/config/db package
nginx/              # nginx config + image build
docker-compose.yml
.env.example
```

## Environment variables

| Variable | Description |
|---|---|
| POSTGRES_PASSWORD | PostgreSQL password |
| STRIPE_SECRET_KEY | Stripe secret key (`sk_test_...`) |
| STRIPE_WEBHOOK_SECRET | Stripe webhook signing secret |
| STRIPE_PRICE_ID | Stripe Price ID for one photo |
| PUBLIC_BASE_URL | Public site URL (for links) |
| ADMIN_TOKEN | Admin API token |
| SITE_NAME | Frontend branding title |
| SITE_TAGLINE | Frontend branding tagline |

## Local development

1) Create env file:

```bash
cp .env.example .env
```

2) Start stack:

```bash
docker compose up -d --build
```

For local data mounts, use `docker-compose.override.yml` (already included in repo).

## API highlights

- Public:
  - `GET /api/events`
  - `GET /api/events/{id}/photos?page=1&bib=123&start_time=09:00&end_time=11:30`
- Checkout:
  - `POST /api/carts`
  - `POST /api/checkout`
- Orders:
  - `GET /api/orders/{id}`
  - `GET /d/{token}`
- Admin:
  - `POST /api/admin/events`
  - `POST /api/admin/events/{id}/ingest`
  - `POST /api/admin/events/{id}/tags/bibs`
  - `GET /api/admin/orders`
  - `POST /api/admin/orders/{id}/reset-delivery`

## Operational notes

- Download links are expiry-limited and count-limited.
- ZIP outputs are generated with readable permissions for nginx delivery.
- If Stripe webhooks are unreachable in dev, the order endpoint includes fallback status fulfillment behavior.

## Testing

Backend tests:

```bash
python -m pytest api/tests -q
```

Frontend build check:

```bash
npm --prefix frontend run build
```
