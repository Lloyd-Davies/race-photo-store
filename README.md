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
- Admin event editing (name/date/location/status)
- Admin order management tools (reset delivery, rebuild ZIP, expire links)
- Admin operational snapshot stats

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
| CLOUDFLARE_TUNNEL_TOKEN | Cloudflare tunnel token used by `cloudflared` |

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

## Production deployment (Oracle + Portainer)

This repository is production-configured to run from GHCR images in `docker-compose.yml`.

1) Prepare host directories on the server:

```bash
sudo mkdir -p /mnt/pstore/{pgdata,redis,photos}
sudo chown -R $USER:$USER /mnt/pstore
```

2) Create a production `.env` from `.env.example` and fill at least:

- `POSTGRES_PASSWORD`
- `PUBLIC_BASE_URL`
- `ADMIN_TOKEN`
- `CLOUDFLARE_TUNNEL_TOKEN`
- Stripe vars (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`) when enabling payments

3) Ensure GHCR images are pullable by your deployment environment:

- Option A: package is public (simplest)
- Option B: package private + registry credentials in Portainer (`ghcr.io`, username, PAT with `read:packages`)

4) In Portainer, deploy/update stack with:

- Compose file: `docker-compose.yml`
- Env file values populated from your `.env`
- Force pull latest images on update

5) Verify service health after deploy:

- `postgres`, `redis`, `api`, `worker`, `nginx`, `cloudflared` are running
- `GET /api/health` returns healthy
- Admin login works with `ADMIN_TOKEN`

6) File/storage expectations:

- Proofs uploaded to: `/mnt/pstore/photos/proofs/<event-slug>/*.jpg`
- Originals uploaded to: `/mnt/pstore/photos/originals/<event-slug>/*.jpg`
- Generated ZIPs in: `/mnt/pstore/photos/zips/`

7) Typical production update flow:

- Push code to `dev` (CI builds/pushes fresh GHCR `:latest` images)
- Redeploy stack in Portainer with pull enabled
- Smoke-test gallery, checkout/order status, and admin actions

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
  - `PATCH /api/admin/events/{id}`
  - `POST /api/admin/events/{id}/ingest`
  - `POST /api/admin/events/{id}/tags/bibs`
  - `GET /api/admin/stats`
  - `GET /api/admin/orders`
  - `POST /api/admin/orders/{id}/reset-delivery`
  - `POST /api/admin/orders/{id}/rebuild-zip`
  - `POST /api/admin/orders/{id}/expire-delivery`

## Release strategy

Recommended workflow:

1) `dev` = active integration branch (feature work, fixes, validation).
2) `main` = stable release branch (only fast-forward/PR merges from validated `dev`).
3) Tag releases from `main` (for example `v0.2.0`) after smoke tests on production-like deploy.

Why this works well here:

- Your CI currently builds/pushes images on both `dev` and `main`.
- Keeping releases tagged from `main` gives you a clean, auditable production line.
- `dev` remains fast for ongoing work while `main` is easier to rollback and communicate.

Suggested release steps:

1) Confirm `dev` is green (tests/build) and deployed successfully to your live/staging stack.
2) Open PR `dev -> main` and merge.
3) Create annotated tag on `main` (`vX.Y.Z`) and push tag.
4) (Optional) Publish GitHub Release notes for that tag.
5) In Portainer, redeploy pinned version if you adopt versioned image tags later; with `:latest`, redeploy immediately after merge.

Image tag behavior from CI:

- `dev` pushes: `dev-latest` and `dev-<shortsha>`
- `main` pushes: `latest` and `main-<shortsha>`
- `v*` tags (for example `v0.1.0`): immutable version tags like `api:v0.1.0`, `worker:v0.1.0`, `nginx:v0.1.0`

Starting version recommendation:

- Use SemVer with a `v` prefix.
- First store release: `v0.1.0` (pre-1.0, feature-complete baseline).

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
