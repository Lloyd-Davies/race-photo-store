def test_list_events_empty(client):
    resp = client.get("/api/events")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_events(client, test_event):
    resp = client.get("/api/events")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["slug"] == test_event.slug
    assert data[0]["name"] == test_event.name


def test_list_events_enforces_visibility_windows(client, db_session):
    from datetime import datetime, timedelta, timezone

    from photostore.models import Event, EventStatus

    now = datetime.now(timezone.utc)
    visible = Event(
        slug="visible-event",
        name="Visible Event",
        date=now,
        status=EventStatus.ACTIVE,
        public_until=now + timedelta(days=2),
        archive_after=now + timedelta(days=7),
    )
    expired_public = Event(
        slug="expired-public-event",
        name="Expired Public",
        date=now,
        status=EventStatus.ACTIVE,
        public_until=now - timedelta(minutes=1),
    )
    archived_status = Event(
        slug="archived-status-event",
        name="Archived Status",
        date=now,
        status=EventStatus.ARCHIVED,
    )
    archived_by_window = Event(
        slug="archive-window-event",
        name="Archive Window",
        date=now,
        status=EventStatus.ACTIVE,
        archive_after=now - timedelta(minutes=1),
    )
    db_session.add_all([visible, expired_public, archived_status, archived_by_window])
    db_session.flush()

    resp = client.get("/api/events")
    assert resp.status_code == 200
    slugs = {event["slug"] for event in resp.json()}
    assert "visible-event" in slugs
    assert "expired-public-event" not in slugs
    assert "archived-status-event" not in slugs
    assert "archive-window-event" not in slugs


def test_list_photos(client, test_event, test_photos):
    resp = client.get(f"/api/events/{test_event.id}/photos")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["photos"]) == 3
    # proof_url must use guarded API proof endpoint
    for photo in data["photos"]:
        assert photo["proof_url"].startswith(f"/api/events/{test_event.id}/photos/")
        assert photo["proof_url"].endswith("/proof")
        assert "photo_id" in photo


def test_list_photos_pagination(client, test_event, test_photos):
    resp = client.get(f"/api/events/{test_event.id}/photos?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["photos"]) == 2
    assert data["total"] == 3
    assert data["pages"] == 2


def test_list_photos_bib_filter(client, db_session, test_event, test_photos):
    from photostore.models import PhotoTag

    db_session.add(PhotoTag(
        photo_id=test_photos[0].id,
        tag_type="bib",
        value="42",
        confidence=0.99,
    ))
    db_session.flush()

    resp = client.get(f"/api/events/{test_event.id}/photos?bib=42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["photos"][0]["photo_id"] == test_photos[0].id


def test_list_photos_unknown_event(client):
    resp = client.get("/api/events/99999/photos")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_photos_hidden_event_returns_empty(client, db_session):
    from datetime import datetime, timezone

    from photostore.models import Event, EventStatus, Photo

    event = Event(
        slug="hidden-event",
        name="Hidden Event",
        date=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        status=EventStatus.ARCHIVED,
    )
    db_session.add(event)
    db_session.flush()

    db_session.add(Photo(
        id="hidden-001",
        event_id=event.id,
        proof_path=f"proofs/{event.slug}/hidden-001.jpg",
        original_path=f"originals/{event.slug}/hidden-001.jpg",
    ))
    db_session.flush()

    resp = client.get(f"/api/events/{event.id}/photos")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_list_photos_time_filter(client, db_session, test_event, test_photos):
    from datetime import datetime, timezone

    test_photos[0].captured_at = datetime(2026, 2, 18, 9, 5, tzinfo=timezone.utc)
    test_photos[1].captured_at = datetime(2026, 2, 18, 9, 45, tzinfo=timezone.utc)
    test_photos[2].captured_at = datetime(2026, 2, 18, 10, 15, tzinfo=timezone.utc)
    db_session.flush()

    resp = client.get(f"/api/events/{test_event.id}/photos?start_time=09:30&end_time=10:00")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["photos"][0]["photo_id"] == test_photos[1].id


def test_list_photos_time_filter_invalid_format(client, test_event, test_photos):
    resp = client.get(f"/api/events/{test_event.id}/photos?start_time=9am")
    assert resp.status_code == 400


def test_list_photos_locked_requires_unlock(client, db_session):
    from datetime import datetime, timezone

    from app.event_access import hash_event_password
    from photostore.models import Event, Photo

    event = Event(
        slug="locked-event",
        name="Locked Event",
        date=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        is_password_protected=True,
        access_password_hash=hash_event_password("secret123"),
        access_hint="Team name",
    )
    db_session.add(event)
    db_session.flush()

    db_session.add(Photo(
        id="locked-001",
        event_id=event.id,
        proof_path=f"proofs/{event.slug}/locked-001.jpg",
        original_path=f"originals/{event.slug}/locked-001.jpg",
    ))
    db_session.flush()

    resp = client.get(f"/api/events/{event.id}/photos")
    assert resp.status_code == 401


def test_unlock_event_and_list_photos(client, db_session):
    from datetime import datetime, timezone

    from app.event_access import hash_event_password
    from photostore.models import Event, Photo

    event = Event(
        slug="locked-event-2",
        name="Locked Event 2",
        date=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        is_password_protected=True,
        access_password_hash=hash_event_password("secret123"),
    )
    db_session.add(event)
    db_session.flush()

    db_session.add(Photo(
        id="locked-002",
        event_id=event.id,
        proof_path=f"proofs/{event.slug}/locked-002.jpg",
        original_path=f"originals/{event.slug}/locked-002.jpg",
    ))
    db_session.flush()

    bad = client.post(f"/api/events/{event.id}/unlock", json={"password": "wrong"})
    assert bad.status_code == 401

    unlock = client.post(f"/api/events/{event.id}/unlock", json={"secret": "secret123"})
    assert unlock.status_code == 200
    token = unlock.json()["access_token"]

    resp = client.get(
        f"/api/events/{event.id}/photos",
        headers={"X-Event-Access": token},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    proof_url = resp.json()["photos"][0]["proof_url"]
    assert f"access_token={token}" in proof_url


def test_get_event_proof_unlocked_event(client, test_event, test_photos):
    photo_id = test_photos[0].id
    resp = client.get(f"/api/events/{test_event.id}/photos/{photo_id}/proof")
    assert resp.status_code == 200
    assert "X-Accel-Redirect" in resp.headers
    assert resp.headers["X-Accel-Redirect"].endswith(f"/{test_event.slug}/{photo_id}.jpg")


def test_get_event_proof_locked_requires_token(client, db_session, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from app.event_access import hash_event_password
    from photostore.config import settings
    from photostore.models import Event, Photo

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    event = Event(
        slug="locked-proof",
        name="Locked Proof",
        date=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        is_password_protected=True,
        access_password_hash=hash_event_password("secret123"),
    )
    db_session.add(event)
    db_session.flush()

    db_session.add(Photo(
        id="locked-proof-001",
        event_id=event.id,
        proof_path=f"proofs/{event.slug}/locked-proof-001.jpg",
        original_path=f"originals/{event.slug}/locked-proof-001.jpg",
    ))
    db_session.flush()

    proof = storage / "proofs" / event.slug / "locked-proof-001.jpg"
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_bytes(b"FAKEJPEG")

    locked = client.get(f"/api/events/{event.id}/photos/locked-proof-001/proof")
    assert locked.status_code == 401

    unlock = client.post(f"/api/events/{event.id}/unlock", json={"password": "secret123"})
    assert unlock.status_code == 200
    token = unlock.json()["access_token"]

    unlocked = client.get(
        f"/api/events/{event.id}/photos/locked-proof-001/proof",
        headers={"X-Event-Access": token},
    )
    assert unlocked.status_code == 200
    assert "X-Accel-Redirect" in unlocked.headers

    unlocked_query = client.get(
        f"/api/events/{event.id}/photos/locked-proof-001/proof?access_token={token}",
    )
    assert unlocked_query.status_code == 200


def test_unlock_hidden_event_returns_not_found(client, db_session):
    from datetime import datetime, timedelta, timezone

    from app.event_access import hash_event_password
    from photostore.models import Event

    now = datetime.now(timezone.utc)
    event = Event(
        slug="hidden-locked-event",
        name="Hidden Locked Event",
        date=now,
        is_password_protected=True,
        access_password_hash=hash_event_password("secret123"),
        public_until=now - timedelta(minutes=1),
    )
    db_session.add(event)
    db_session.flush()

    resp = client.post(f"/api/events/{event.id}/unlock", json={"secret": "secret123"})
    assert resp.status_code == 404


def test_get_event_proof_hidden_event_returns_not_found(client, db_session, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from photostore.config import settings
    from photostore.models import Event, EventStatus, Photo

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    event = Event(
        slug="hidden-proof-event",
        name="Hidden Proof Event",
        date=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        status=EventStatus.ARCHIVED,
    )
    db_session.add(event)
    db_session.flush()

    db_session.add(Photo(
        id="hidden-proof-001",
        event_id=event.id,
        proof_path=f"proofs/{event.slug}/hidden-proof-001.jpg",
        original_path=f"originals/{event.slug}/hidden-proof-001.jpg",
    ))
    db_session.flush()

    proof = storage / "proofs" / event.slug / "hidden-proof-001.jpg"
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_bytes(b"FAKEJPEG")

    resp = client.get(f"/api/events/{event.id}/photos/hidden-proof-001/proof")
    assert resp.status_code == 404
