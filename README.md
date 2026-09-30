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
- Local development uses the isolated `compose.local.yml` through `scripts/local.ps1`.

## Quick start (local)

Use the isolated development stack; it does not read production `.env` or start a Tunnel.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -ContainersOnly
powershell -ExecutionPolicy Bypass -File scripts/local.ps1 start
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
curl.exe http://127.0.0.1:18081/api/healthz
```

Production uses `docker-compose.yml`;
local development uses standalone `compose.local.yml` through the wrapper.

## Production (current compose)

1) Prepare host dirs:

```bash
sudo mkdir -p /mnt/pstore/{pgdata,redis,photos}
sudo chown -R $USER:$USER /mnt/pstore
```

2) Set required env:

- `POSTGRES_PASSWORD`
- `PUBLIC_BASE_URL`
- `SEO_SITE_URL=https://photos.example.com`
- `ADMIN_TOKEN`
- `CLOUDFLARE_TUNNEL_TOKEN`
- `IMAGE_TAG` set to a verified commit-specific tag; record image digests

3) Optional but recommended:

- `ADMIN_SESSION_SECRET`
- Stripe vars (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`)
- Email vars (`EMAIL_ENABLED`, `BREVO_API_KEY`, `EMAIL_FROM_ADDRESS`, `SUPPORT_EMAIL`)

4) Deploy `docker-compose.yml` (Portainer or Docker), then verify:

- `GET /api/healthz` returns healthy
- admin login works
- gallery, checkout, and download flow work end-to-end
- Brevo test email arrives and all email links use the public app domain
- Stripe webhook is configured to `https://your-domain/api/stripe/webhook`
- Cloudflare public hostname points to the tunnel service URL for nginx

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
- `GET /api/admin/orders/{id}`
- `GET /api/admin/settings`

## Configuration

Primary env vars:

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `PUBLIC_BASE_URL` | Public URL used in generated links |
| `SEO_SITE_URL` | Public HTTPS origin used only for canonical and sitemap URLs; must not be localhost or an internal host |
| `ADMIN_TOKEN` | Base admin credential for login |
| `ADMIN_SESSION_SECRET` | Signing key for admin/event/order access tokens |
| `CLOUDFLARE_TUNNEL_TOKEN` | Cloudflare tunnel connector token |
| `IMAGE_TAG` | GHCR image tag to deploy; use a pinned release tag in production |

SEO/branding variables:

| Variable | Production value/purpose |
|---|---|
| `SITE_NAME` | `Race Photos` |
| `SITE_TAGLINE` | Optional visible tagline |
| `SEO_DEFAULT_TITLE` | Default homepage/browser title |
| `SEO_TITLE_TEMPLATE` | Page-title template using `{page}` and `{site_name}` |
| `SEO_DEFAULT_DESCRIPTION` | Default search/social description |
| `SEO_LOGO_URL` | Absolute public logo URL |

`PUBLIC_BASE_URL` remains separate because local checkout and email testing may
use localhost. Canonicals, structured data and the sitemap use only validated
`SEO_*` URLs and reject local/private hosts.

Public event pages use the event cover for Open Graph/Twitter previews when a
cover exists. The homepage, protected galleries, and events without covers
omit image metadata rather than publishing a generic or private fallback.

Checkout pricing is managed in Admin Settings. Events can inherit the global
photo price or define their own override. Stripe promotion codes are managed in
Stripe and can be enabled for Checkout from Admin Settings.

Email env vars:

| Variable | Purpose |
|---|---|
| `EMAIL_ENABLED` | Enables transactional email sending |
| `BREVO_API_KEY` | Brevo transactional API key |
| `EMAIL_FROM_ADDRESS` | Verified sender address |
| `EMAIL_FROM_NAME` | Sender display name |
| `SUPPORT_EMAIL` | Support address included in templates |
| `ORDER_EMAIL_REQUIRED` | Requires checkout email when true |
| `BREVO_WEBHOOK_SECRET` | Shared secret reserved for Brevo webhook handling |

Security tuning:

| Variable | Default |
|---|---|
| `ADMIN_SESSION_TTL_MINUTES` | `30` |
| `ADMIN_REFRESH_TTL_HOURS` | `12` |
| `EVENT_ACCESS_TTL_HOURS` | `12` |
| `ORDER_ACCESS_TTL_HOURS` | `720` |
| `MAX_PHOTO_UPLOAD_BYTES` | `104857600` |

## Validation

```bash
python -m pytest api/tests -q
python -m pytest worker/tests -q
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
docker compose --env-file scripts/local.env -p race-photo-local -f compose.local.yml config --quiet
docker build -f api/Dockerfile -t photostore-api:seo .
docker build -f nginx/Dockerfile -t photostore-nginx:seo .
docker run --rm photostore-nginx:seo nginx -t
```

## CI and releases

- `.github/workflows/ci.yml` runs API, worker, backup/restore and frontend tests, frontend typecheck, and frontend build.
- `.github/workflows/build.yml` pushes GHCR images for `api`, `worker`, `nginx` and the independently deployed `backup` service only after test jobs pass.
- Branch pushes publish mutable dev/main tags; production should deploy commit-specific image tags and record their digests.

## Repo layout

```text
api/                FastAPI application
worker/             Celery tasks
frontend/           React app
shared/photostore/  Shared models/config/db
nginx/              Nginx config and image
```
