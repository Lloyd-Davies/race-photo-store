import json
import re
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import pytest

from photostore.models import Event, EventStatus

PRODUCTION_URL = "https://photos.example.com"


@pytest.fixture(autouse=True)
def synthetic_site_settings(db_engine, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "SEO_SITE_URL", PRODUCTION_URL)
    monkeypatch.setattr(settings, "SEO_LOGO_URL", f"{PRODUCTION_URL}/favicon.svg")


@pytest.mark.parametrize(
    "invalid_url",
    ["http://localhost:8080", "https://api.internal", "https://127.0.0.1",
     "https://photos.example.com/subpath", "https://photos.example.com?query=1",
     "https://photos.example.com#fragment", "https://user:password@photos.example.com"],
)
def test_seo_site_url_rejects_local_and_internal_hosts(invalid_url, db_engine):
    from pydantic import ValidationError
    from photostore.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="postgresql+psycopg://example.invalid/test",
            REDIS_URL="redis://example.invalid/0",
            SEO_SITE_URL=invalid_url,
        )


def test_branding_and_origin_are_runtime_configuration():
    from photostore.config import Settings
    configured = Settings(_env_file=None,
        DATABASE_URL="postgresql+psycopg://example.invalid/test", REDIS_URL="redis://example.invalid/0",
        SITE_NAME="Synthetic Event Store", SEO_SITE_URL="https://events.example.org/",
        SEO_LOGO_URL="")
    assert configured.SITE_NAME == "Synthetic Event Store"
    assert configured.SEO_SITE_URL == "https://events.example.org"
    assert configured.SEO_LOGO_URL == "https://events.example.org/favicon.svg"
    assert configured.SEO_DEFAULT_TITLE == "Synthetic Event Store | Race and Event Photos"


def test_explicit_public_logo_can_use_another_origin():
    from photostore.config import Settings
    configured = Settings(_env_file=None,
        DATABASE_URL="postgresql+psycopg://example.invalid/test", REDIS_URL="redis://example.invalid/0",
        SEO_SITE_URL="https://events.example.org", SEO_LOGO_URL="https://cdn.example.org/logo.svg")
    assert configured.SEO_LOGO_URL == "https://cdn.example.org/logo.svg"


@pytest.mark.parametrize("public_url,expected", [
    ("https://events.example.org/", "https://events.example.org"),
    ("http://127.0.0.1:18081", "https://photos.example.com"),
])
def test_minimal_configuration_derives_metadata_and_sender(public_url, expected):
    from photostore.config import Settings
    configured = Settings(_env_file=None,
        DATABASE_URL="postgresql+psycopg://example.invalid/test", REDIS_URL="redis://example.invalid/0",
        PUBLIC_BASE_URL=public_url, SITE_NAME="Synthetic Store", SEO_SITE_URL="",
        SEO_LOGO_URL="", SEO_DEFAULT_TITLE="", EMAIL_FROM_NAME="")
    assert configured.SEO_SITE_URL == expected
    assert configured.SEO_LOGO_URL == f"{expected}/favicon.svg"
    assert configured.SEO_DEFAULT_TITLE == "Synthetic Store | Race and Event Photos"
    assert configured.EMAIL_FROM_NAME == "Synthetic Store"


def test_explicit_metadata_and_sender_override_derived_defaults():
    from photostore.config import Settings
    configured = Settings(_env_file=None,
        DATABASE_URL="postgresql+psycopg://example.invalid/test", REDIS_URL="redis://example.invalid/0",
        PUBLIC_BASE_URL="https://events.example.org", SEO_SITE_URL="https://search.example.org",
        SEO_LOGO_URL="https://cdn.example.org/logo.svg", SEO_DEFAULT_TITLE="Custom title",
        EMAIL_FROM_NAME="Custom sender")
    assert configured.SEO_SITE_URL == "https://search.example.org"
    assert configured.SEO_DEFAULT_TITLE == "Custom title"
    assert configured.EMAIL_FROM_NAME == "Custom sender"


@pytest.mark.parametrize("template", ["{unknown}", "{page", "{page.__class__}"])
def test_invalid_title_templates_fail_at_setup(template):
    from pydantic import ValidationError
    from photostore.config import Settings
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DATABASE_URL="postgresql+psycopg://example.invalid/test",
                 REDIS_URL="redis://example.invalid/0", SEO_TITLE_TEMPLATE=template)


def _structured_data(html: str):
    match = re.search(
        r'<script id="seo-structured-data" type="application/ld\+json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


def test_robots_is_plain_text_and_not_the_spa_shell(client):
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; charset=utf-8")
    assert "<!doctype html>" not in response.text.lower()
    assert '<div id="root">' not in response.text
    assert "User-agent: *" in response.text
    assert f"Sitemap: {PRODUCTION_URL}/sitemap.xml" in response.text
    assert "Allow: /proofs/" in response.text
    assert "Disallow: /api/" in response.text


def test_sitemap_contains_only_public_gallery_pages(client, db_session, test_event):
    private = Event(
        slug="private-event",
        name="Private Event",
        date=datetime(2026, 4, 1, tzinfo=timezone.utc),
        is_password_protected=True,
    )
    expired = Event(
        slug="expired-event",
        name="Expired Event",
        date=datetime(2025, 4, 1, tzinfo=timezone.utc),
        public_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    archived = Event(
        slug="archived-event",
        name="Archived Event",
        date=datetime(2024, 4, 1, tzinfo=timezone.utc),
        status=EventStatus.ARCHIVED,
    )
    db_session.add_all([private, expired, archived])
    db_session.flush()

    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    root = ElementTree.fromstring(response.content)
    locations = [node.text for node in root.findall("{*}url/{*}loc")]
    assert f"{PRODUCTION_URL}/" in locations
    assert f"{PRODUCTION_URL}/events/{test_event.slug}" in locations
    assert not any("private-event" in url for url in locations)
    assert not any("expired-event" in url for url in locations)
    assert not any("archived-event" in url for url in locations)
    assert not any(part in url for url in locations for part in ("localhost", "/admin", "/cart", "/checkout"))


def test_homepage_has_initial_metadata_schema_heading_and_event_link(client, test_event):
    response = client.get("/")

    assert response.status_code == 200
    assert "Race Photos | Race and Event Photos" in response.text
    assert f'<link rel="canonical" href="{PRODUCTION_URL}/"' in response.text
    assert '<meta name="description"' in response.text
    assert '<meta name="robots" content="index, follow, max-image-preview:large"' in response.text
    assert "<h1>Race Photos</h1>" in response.text
    assert f'href="/events/{test_event.slug}"' in response.text
    assert _structured_data(response.text)["@type"] == "Organization"


def test_public_gallery_has_unique_metadata_and_valid_json_ld(client, db_session, test_event):
    test_event.location = "Hereford"
    second = Event(
        slug="test-event-two",
        name=test_event.name,
        date=test_event.date + timedelta(days=1),
        location="Hereford",
    )
    db_session.add(second)
    db_session.flush()

    first_response = client.get(f"/events/{test_event.slug}")
    second_response = client.get(f"/events/{second.slug}")
    first_title = re.search(r"<title>(.*?)</title>", first_response.text).group(1)
    second_title = re.search(r"<title>(.*?)</title>", second_response.text).group(1)

    assert first_response.status_code == 200
    assert first_title != second_title
    assert f'<link rel="canonical" href="{PRODUCTION_URL}/events/{test_event.slug}"' in first_response.text
    assert "Hereford" in first_response.text
    assert "by Race Photos" in first_response.text
    schema = _structured_data(first_response.text)
    assert {entry["@type"] for entry in schema} == {"CollectionPage", "BreadcrumbList"}


def test_private_gallery_is_noindex_and_absent_from_structured_data(client, test_event):
    test_event.is_password_protected = True

    response = client.get(f"/events/{test_event.slug}")

    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert '<meta name="robots" content="noindex, nofollow, noarchive"' in response.text
    assert "seo-structured-data" not in response.text


def test_gallery_uses_real_cover_and_omits_image_metadata_without_one(client, test_event):
    without_cover = client.get(f"/events/{test_event.slug}")
    assert 'property="og:image"' not in without_cover.text
    assert 'name="twitter:image"' not in without_cover.text

    test_event.cover_path = f"covers/{test_event.slug}/cover.jpg"
    with_cover = client.get(f"/events/{test_event.slug}")
    expected = f"{PRODUCTION_URL}/covers/{test_event.slug}.jpg"
    assert f'<meta property="og:image" content="{expected}"' in with_cover.text
    schema = _structured_data(with_cover.text)
    collection = next(entry for entry in schema if entry["@type"] == "CollectionPage")
    assert collection["mainEntity"]["image"] == expected


def test_missing_and_case_variant_galleries_return_real_404(client, test_event):
    missing = client.get("/events/does-not-exist")
    case_variant = client.get(f"/events/{test_event.slug.upper()}")

    assert missing.status_code == 404
    assert case_variant.status_code == 404
    assert "Gallery not found" in missing.text
    assert missing.headers["x-robots-tag"] == "noindex, nofollow, noarchive"


def test_legacy_id_and_trailing_slash_redirect_permanently(client, test_event):
    by_id = client.get(f"/events/{test_event.id}", follow_redirects=False)
    slash = client.get(f"/events/{test_event.slug}/", follow_redirects=False)

    assert by_id.status_code == 308
    assert by_id.headers["location"] == f"/events/{test_event.slug}"
    assert slash.status_code == 308
    assert slash.headers["location"] == f"/events/{test_event.slug}"


def test_query_variants_use_clean_canonical_and_appropriate_robots(client, test_event):
    filtered = client.get(f"/events/{test_event.slug}?bib=123")
    tracked = client.get(f"/events/{test_event.slug}?utm_source=newsletter")

    canonical = f'<link rel="canonical" href="{PRODUCTION_URL}/events/{test_event.slug}"'
    assert canonical in filtered.text
    assert filtered.headers["x-robots-tag"] == "noindex, follow"
    assert tracked.headers["x-robots-tag"] == "index, follow, max-image-preview:large"


def test_homepage_metadata_survives_event_query_failure(client, db_session, monkeypatch):
    monkeypatch.setattr(db_session, "query", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")))

    response = client.get("/")

    assert response.status_code == 200
    assert "Race Photos | Race and Event Photos" in response.text
    assert "localhost" not in response.text


def test_manifest_uses_public_branding(client):
    response = client.get("/site.webmanifest")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/manifest+json")
    assert response.json()["name"] == "Race Photos"


def test_api_and_download_responses_are_noindex(client):
    api_response = client.get("/api/config")
    download_response = client.get("/d/not-a-token")

    assert api_response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
    assert download_response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
