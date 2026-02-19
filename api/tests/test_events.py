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
