def test_healthz(client):
    resp = client.get("/api/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
