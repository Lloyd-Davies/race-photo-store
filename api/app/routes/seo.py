import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.deps import get_db
from app.routes.events import _is_event_publicly_visible
from photostore.config import settings
from photostore.models import Event, EventStatus

router = APIRouter(tags=["seo"])
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

INDEX_ROBOTS = "index, follow, max-image-preview:large"
NOINDEX_FOLLOW = "noindex, follow"
PRIVATE_ROBOTS = "noindex, nofollow, noarchive"
TRACKING_QUERY_KEYS = {"gclid", "dclid", "fbclid", "msclkid"}
DUPLICATE_QUERY_KEYS = {
    "bib",
    "page",
    "sort",
    "filter",
    "start_time",
    "end_time",
    "photo",
    "lightbox",
    "purchase",
    "checkout",
}


def _absolute(path: str = "/") -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{settings.SEO_SITE_URL}{path}"


def _format_date(value: datetime) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _event_title(event: Event) -> str:
    page = f"{event.name} – {_format_date(event.date)} Photos"
    return settings.SEO_TITLE_TEMPLATE.format(page=page, site_name=settings.SITE_NAME)


def _event_description(event: Event) -> str:
    location = f" at {event.location}" if event.location else ""
    return (
        f"Browse and purchase photographs from {event.name}, photographed on "
        f"{_format_date(event.date)}{location} by {settings.SITE_NAME}."
    )


def _query_robots(request: Request, default: str = INDEX_ROBOTS) -> str:
    keys = {key.lower() for key in request.query_params.keys()}
    if not keys:
        return default
    if all(key.startswith("utm_") or key in TRACKING_QUERY_KEYS for key in keys):
        return default
    if keys & DUPLICATE_QUERY_KEYS or keys:
        return NOINDEX_FOLLOW
    return default


def _organization_schema() -> dict:
    data: dict = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": settings.SITE_NAME,
        "url": settings.SEO_SITE_URL,
        "logo": settings.SEO_LOGO_URL,
        "description": settings.SEO_DEFAULT_DESCRIPTION,
    }
    if settings.SUPPORT_EMAIL:
        data["email"] = settings.SUPPORT_EMAIL
    return data


def _gallery_schema(
    event: Event,
    canonical: str,
    description: str,
    image: str | None,
) -> list[dict]:
    gallery: dict = {
        "@type": "ImageGallery",
        "name": f"{event.name} photo gallery",
        "description": description,
        "url": canonical,
    }
    if image:
        gallery["image"] = image
    return [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": event.name,
            "description": description,
            "url": canonical,
            "isPartOf": {"@type": "WebSite", "name": settings.SITE_NAME, "url": settings.SEO_SITE_URL},
            "mainEntity": gallery,
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Events", "item": _absolute("/")},
                {"@type": "ListItem", "position": 2, "name": event.name, "item": canonical},
            ],
        },
    ]


def _render_page(
    request: Request,
    *,
    title: str,
    description: str,
    canonical: str,
    robots: str,
    page_kind: str,
    status_code: int = 200,
    event: Event | None = None,
    public_events: list[Event] | None = None,
    structured_data: dict | list[dict] | None = None,
    social_image: str | None = None,
) -> HTMLResponse:
    response = templates.TemplateResponse(
        request=request,
        name="seo_page.html",
        context={
            "title": title,
            "description": description,
            "canonical": canonical,
            "robots": robots,
            "site_name": settings.SITE_NAME,
            "page_kind": page_kind,
            "event": event,
            "event_date": _format_date(event.date) if event else None,
            "event_description": _event_description(event) if event else None,
            "public_events": public_events or [],
            "structured_data": structured_data,
            "social_image": social_image,
            "logo_url": settings.SEO_LOGO_URL,
        },
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "X-Robots-Tag": robots,
        },
    )
    return response


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> PlainTextResponse:
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Allow: /events/",
            "Allow: /covers/",
            "Allow: /proofs/",
            "Disallow: /admin",
            "Disallow: /api/",
            "Disallow: /cart",
            "Disallow: /orders/",
            "Disallow: /d/",
            "",
            f"Sitemap: {_absolute('/sitemap.xml')}",
            "",
        ]
    )
    return PlainTextResponse(
        body,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/sitemap.xml")
def sitemap_xml(db: Session = Depends(get_db)) -> Response:
    now = datetime.now(timezone.utc)
    try:
        events = (
            db.query(Event)
            .filter(Event.status == EventStatus.ACTIVE)
            .filter(Event.is_password_protected.is_(False))
            .filter(or_(Event.public_until.is_(None), Event.public_until >= now))
            .filter(or_(Event.archive_after.is_(None), Event.archive_after > now))
            .order_by(Event.date.desc(), Event.slug.asc())
            .all()
        )
    except Exception:
        logger.exception("Could not generate sitemap")
        return Response(
            "Sitemap temporarily unavailable",
            status_code=503,
            media_type="text/plain",
            headers={"Retry-After": "300", "X-Robots-Tag": PRIVATE_ROBOTS},
        )

    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ElementTree.register_namespace("", namespace)
    urlset = ElementTree.Element(f"{{{namespace}}}urlset")
    for url in [_absolute("/"), *[_absolute(f"/events/{quote(event.slug, safe='')}") for event in events]]:
        node = ElementTree.SubElement(urlset, f"{{{namespace}}}url")
        ElementTree.SubElement(node, f"{{{namespace}}}loc").text = url
    body = ElementTree.tostring(urlset, encoding="utf-8", xml_declaration=True)
    return Response(body, media_type="application/xml", headers={"Cache-Control": "public, max-age=300"})


@router.get("/site.webmanifest")
def site_manifest() -> JSONResponse:
    return JSONResponse(
        {
            "name": settings.SITE_NAME,
            "short_name": settings.SITE_NAME,
            "description": settings.SEO_DEFAULT_DESCRIPTION,
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#020617",
            "theme_color": "#0ea5e9",
            "icons": [{"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
        },
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/", response_class=HTMLResponse)
def homepage(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    now = datetime.now(timezone.utc)
    try:
        events = (
            db.query(Event)
            .filter(Event.status == EventStatus.ACTIVE)
            .filter(Event.is_password_protected.is_(False))
            .filter(or_(Event.public_until.is_(None), Event.public_until >= now))
            .filter(or_(Event.archive_after.is_(None), Event.archive_after > now))
            .order_by(Event.date.desc(), Event.slug.asc())
            .all()
        )
    except Exception:
        logger.exception("Could not load public events for initial homepage HTML")
        events = []
    return _render_page(
        request,
        title=settings.SEO_DEFAULT_TITLE,
        description=settings.SEO_DEFAULT_DESCRIPTION,
        canonical=_absolute("/"),
        robots=_query_robots(request),
        page_kind="home",
        public_events=events,
        structured_data=_organization_schema(),
    )


@router.get("/events/{event_ref}", response_class=HTMLResponse)
@router.get("/events/{event_ref}/", response_class=HTMLResponse, include_in_schema=False)
def event_page(event_ref: str, request: Request, db: Session = Depends(get_db)) -> Response:
    try:
        event = db.query(Event).filter(Event.slug == event_ref).first()
        if event is None and event_ref.isdigit():
            event = db.query(Event).filter(Event.id == int(event_ref)).first()
    except Exception:
        logger.exception("Could not load event metadata", extra={"event_ref": event_ref})
        return _render_page(
            request,
            title=settings.SEO_TITLE_TEMPLATE.format(page="Gallery unavailable", site_name=settings.SITE_NAME),
            description="This gallery is temporarily unavailable.",
            canonical=_absolute(f"/events/{quote(event_ref, safe='')}"),
            robots=PRIVATE_ROBOTS,
            page_kind="unavailable",
            status_code=503,
        )

    if not event or not _is_event_publicly_visible(event):
        return _render_page(
            request,
            title=settings.SEO_TITLE_TEMPLATE.format(page="Gallery not found", site_name=settings.SITE_NAME),
            description="The requested gallery could not be found.",
            canonical=_absolute(f"/events/{quote(event_ref, safe='')}"),
            robots=PRIVATE_ROBOTS,
            page_kind="not_found",
            status_code=404,
        )

    canonical_path = f"/events/{quote(event.slug, safe='')}"
    if event_ref != event.slug or request.url.path.endswith("/"):
        return RedirectResponse(canonical_path, status_code=308)

    canonical = _absolute(canonical_path)
    description = _event_description(event)
    is_private = bool(event.is_password_protected)
    social_image = (
        _absolute(f"/covers/{quote(event.slug, safe='')}.jpg")
        if event.cover_path and not is_private
        else None
    )
    return _render_page(
        request,
        title=_event_title(event),
        description=description,
        canonical=canonical,
        robots=PRIVATE_ROBOTS if is_private else _query_robots(request),
        page_kind="private_event" if is_private else "event",
        event=event,
        structured_data=None if is_private else _gallery_schema(event, canonical, description, social_image),
        social_image=social_image,
    )


def _transactional_page(request: Request, page: str) -> HTMLResponse:
    return _render_page(
        request,
        title=settings.SEO_TITLE_TEMPLATE.format(page=page, site_name=settings.SITE_NAME),
        description=settings.SEO_DEFAULT_DESCRIPTION,
        canonical=_absolute(request.url.path.rstrip("/") or "/"),
        robots=PRIVATE_ROBOTS,
        page_kind="transactional",
    )


@router.get("/cart", response_class=HTMLResponse)
def cart_page(request: Request) -> HTMLResponse:
    return _transactional_page(request, "Cart")


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_page(order_id: int, request: Request) -> HTMLResponse:
    return _transactional_page(request, "Order")


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/{path:path}", response_class=HTMLResponse)
def admin_page(request: Request, path: str = "") -> HTMLResponse:
    return _transactional_page(request, "Admin")
