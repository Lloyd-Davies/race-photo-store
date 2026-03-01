def test_unlock_rate_limit_returns_429(client, db_session, monkeypatch):
    from datetime import datetime, timezone

    import app.routes.events as events_route
    from app.event_access import hash_event_password
    from photostore.models import Event

    event = Event(
        slug="locked-rate-limit",
        name="Locked",
        date=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        is_password_protected=True,
        access_password_hash=hash_event_password("secret123"),
    )
    db_session.add(event)
    db_session.flush()

    original_enforce = events_route.enforce_rate_limit
    calls = {"n": 0}

    def fake_enforce(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 2:
            from fastapi import HTTPException

            raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.")

    monkeypatch.setattr(events_route, "enforce_rate_limit", fake_enforce)

    for _ in range(2):
        resp = client.post(f"/api/events/{event.id}/unlock", json={"password": "wrong"})
        assert resp.status_code == 401

    blocked = client.post(f"/api/events/{event.id}/unlock", json={"password": "wrong"})
    assert blocked.status_code == 429

    monkeypatch.setattr(events_route, "enforce_rate_limit", original_enforce)
