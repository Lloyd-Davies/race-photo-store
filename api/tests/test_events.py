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


def test_list_photos(client, test_event, test_photos):
    resp = client.get(f"/api/events/{test_event.id}/photos")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["photos"]) == 3
    # proof_url must start with /proofs/
    for photo in data["photos"]:
        assert photo["proof_url"].startswith("/proofs/")
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
