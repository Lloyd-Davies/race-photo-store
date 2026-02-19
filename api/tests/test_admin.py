from datetime import datetime, timezone


# ── Create event ──────────────────────────────────────────────────────────────

def test_create_event(admin_client):
    resp = admin_client.post("/api/admin/events", json={
        "slug": "spring-5k",
        "name": "Spring 5K 2026",
        "date": "2026-03-01T09:00:00Z",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "spring-5k"
    assert "id" in data


def test_create_event_duplicate_slug(admin_client, test_event):
    resp = admin_client.post("/api/admin/events", json={
        "slug": test_event.slug,
        "name": "Duplicate",
        "date": "2026-03-01T09:00:00Z",
    })
    assert resp.status_code == 409


def test_create_event_requires_admin_token(client):
    resp = client.post("/api/admin/events", json={
        "slug": "no-auth",
        "name": "No Auth",
        "date": "2026-03-01T09:00:00Z",
    })
    assert resp.status_code == 401


# ── Ingest ────────────────────────────────────────────────────────────────────

def test_ingest_photos(admin_client, test_event, tmp_path, monkeypatch):
    import os
    from photostore.config import settings

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    for i in range(1, 4):
        pid = f"img-{i:03d}"
        proof = storage / "proofs" / test_event.slug / f"{pid}.jpg"
        original = storage / "originals" / test_event.slug / f"{pid}.jpg"
        proof.parent.mkdir(parents=True, exist_ok=True)
        original.parent.mkdir(parents=True, exist_ok=True)
        proof.write_bytes(b"FAKEJPEG")
        original.write_bytes(b"FAKEJPEG")

    resp = admin_client.post(f"/api/admin/events/{test_event.id}/ingest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ingested"] == 3
    assert data["skipped"] == 0


def test_ingest_skips_existing_photos(admin_client, test_event, test_photos):
    # test_photos fixture monkeypatches STORAGE_ROOT and creates files + DB rows.
    # Calling ingest again should skip all 3 existing photos.
    resp = admin_client.post(f"/api/admin/events/{test_event.id}/ingest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] == 3
    assert data["ingested"] == 0


def test_ingest_unknown_event(admin_client):
    resp = admin_client.post("/api/admin/events/99999/ingest")
    assert resp.status_code == 404


# ── Bib tags ──────────────────────────────────────────────────────────────────

def test_upload_bib_tags(admin_client, test_event, test_photos):
    resp = admin_client.post(
        f"/api/admin/events/{test_event.id}/tags/bibs",
        json={"tags": [
            {"photo_id": test_photos[0].id, "bib": "42", "confidence": 0.99},
            {"photo_id": test_photos[1].id, "bib": "7",  "confidence": 0.85},
        ]},
    )
    assert resp.status_code == 200
    assert resp.json()["added"] == 2


def test_upload_bib_tags_idempotent(admin_client, test_event, test_photos):
    payload = {"tags": [{"photo_id": test_photos[0].id, "bib": "42", "confidence": 0.99}]}
    admin_client.post(f"/api/admin/events/{test_event.id}/tags/bibs", json=payload)
    resp = admin_client.post(f"/api/admin/events/{test_event.id}/tags/bibs", json=payload)
    assert resp.status_code == 200
    assert resp.json()["added"] == 0  # duplicate, not re-added
