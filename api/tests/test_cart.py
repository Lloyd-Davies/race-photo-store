def test_create_cart(client, test_event, test_photos):
    resp = client.post("/api/carts", json={
        "event_id": test_event.id,
        "photo_ids": [p.id for p in test_photos],
        "email": "runner@example.com",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    assert "cart_id" in data


def test_create_cart_deduplicates(client, test_event, test_photos):
    ids = [test_photos[0].id, test_photos[0].id, test_photos[1].id]
    resp = client.post("/api/carts", json={
        "event_id": test_event.id,
        "photo_ids": ids,
    })
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


def test_create_cart_empty(client, test_event):
    resp = client.post("/api/carts", json={
        "event_id": test_event.id,
        "photo_ids": [],
    })
    assert resp.status_code == 400


def test_create_cart_unknown_photo(client, test_event):
    resp = client.post("/api/carts", json={
        "event_id": test_event.id,
        "photo_ids": ["nonexistent-photo"],
    })
    assert resp.status_code == 400


def test_create_cart_wrong_event(client, test_event, test_photos, db_session):
    from photostore.models import Event
    from datetime import datetime, timezone

    other = Event(
        slug="other-event",
        name="Other",
        date=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    db_session.add(other)
    db_session.flush()

    resp = client.post("/api/carts", json={
        "event_id": other.id,
        "photo_ids": [test_photos[0].id],  # belongs to test_event, not other
    })
    assert resp.status_code == 400
