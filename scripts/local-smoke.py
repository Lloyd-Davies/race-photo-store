"""Run the desktop upload worker against the isolated local server only."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import sys
import time
from unittest.mock import patch
from uuid import uuid4
import zipfile

BASE = "http://127.0.0.1:18081"
TOKEN = "local-only-admin"
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preprocessor", type=Path, default=ROOT.parent / "race-photo-preprocessor")
    args = parser.parse_args()
    sys.path.insert(0, str(args.preprocessor.resolve()))
    import httpx
    from PIL import Image
    from PySide6.QtCore import QCoreApplication
    import preprocessor.config as cfg
    from preprocessor import store_api
    from preprocessor.workers.deploy_worker import DeployWorker

    app = QCoreApplication.instance() or QCoreApplication([])
    with httpx.Client(base_url=BASE, timeout=30, trust_env=False, follow_redirects=False) as client:
        # Refuse any endpoint other than the dedicated local stack before writes.
        config = client.get("/api/config")
        config.raise_for_status()
        assert config.json()["site_name"] == "Local synthetic photo store", "Not the local stack"
        login = client.post("/api/admin/login", json={"admin_token": TOKEN})
        login.raise_for_status()
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        slug = "smoke-" + uuid4().hex[:12]
        created = client.post("/api/admin/events", headers=headers, json={
            "slug": slug, "name": "Synthetic collaboration smoke", "date": datetime.now(timezone.utc).isoformat(),
            "photo_price_pence": 0,
        })
        created.raise_for_status()
        event_id = created.json()["id"]
        output = ROOT / ".localdata" / "collaboration" / "uploader"
        ids = [f"{slug}-a", f"{slug}-b"]
        for kind in ("proofs", "originals"):
            for photo_id in ids:
                path = output / kind / slug / f"{photo_id}.jpg"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (120, 80), "navy").save(path, "JPEG")

        def run_worker(**kwargs):
            worker = DeployWorker(upload_bibs=False, max_workers=1, **kwargs)
            finished, results = [], []
            worker.finished.connect(lambda ok, message: finished.append((ok, message)))
            worker.verification.connect(results.append)
            worker.run()  # Signals delivered synchronously; transport still uses actual API.
            assert finished, "Desktop worker did not report a result"
            return finished[-1], results[-1] if results else None

        actual_upload = store_api.upload_photo
        calls = []

        def interrupted_upload(url, token, event, photo_id, kind, path):
            calls.append((photo_id, kind))
            if photo_id == ids[1] and kind == "original":
                raise httpx.ConnectError("Synthetic disconnected transfer")
            return actual_upload(url, token, event, photo_id, kind, path)

        with ExitStack() as stack:
            for name, value in {"get_store_url": BASE, "get_admin_credential": TOKEN,
                                "get_event_slug": slug, "get_output_root": str(output)}.items():
                stack.enter_context(patch.object(cfg, name, return_value=value))
            # Verify initial absence, then fail one original without losing successful work.
            before = store_api.get_photo_upload_statuses(BASE, TOKEN, event_id, ids)
            assert all(not row.record_exists for row in before.values()) and len(before) == 2
            with patch.object(store_api, "upload_photo", side_effect=interrupted_upload):
                result, verification = run_worker()
            assert not result[0], "Interrupted transfer must report incomplete upload"
            statuses = store_api.get_photo_upload_statuses(BASE, TOKEN, event_id, ids)
            assert all(row.proof_file_exists for row in statuses.values())
            assert statuses[ids[0]].original_file_exists and not statuses[ids[1]].original_file_exists
            result, verification = run_worker(operation="verify")
            assert verification and verification.missing_upload_count == 1
            missing = output / "originals" / slug / f"{ids[1]}.jpg"
            result, verification = run_worker(operation="upload_missing", missing_originals=[missing])
            assert result[0] and verification.missing_upload_count == 0, result[1]
            with patch.object(store_api, "upload_photo", wraps=actual_upload) as spy:
                result, verification = run_worker()
                assert result[0] and spy.call_count == 0, "Repeat upload resent complete assets"
            tags = store_api.upload_bib_tags(BASE, TOKEN, event_id, [{"photo_id": ids[0], "bib": "123", "confidence": 1.0}])
            assert tags["added"] == 1

        # Exercise customer delivery locally with free checkout, never Stripe/email.
        response = client.post("/api/carts", json={"event_id": event_id, "photo_ids": ids})
        response.raise_for_status()
        response = client.post("/api/checkout", json={"cart_id": response.json()["cart_id"], "email": "smoke@example.com"})
        response.raise_for_status()
        checkout = response.json()
        order_id = checkout["order_id"]
        params = {"access_token": checkout["order_access_token"]}
        assert client.get(f"/api/orders/{order_id}").status_code == 404
        order = client.get(f"/api/orders/{order_id}", params=params)
        order.raise_for_status()
        assert order.json()["status"] == "READY"
        for item in order.json()["items"]:
            url = item["download_url"]
            assert url.startswith(BASE + "/d/"), "Refusing a non-local download URL"
            original = client.get(url)
            original.raise_for_status()
            assert original.headers["content-type"].startswith("image/jpeg")
        requested = client.post(f"/api/orders/{order_id}/zip", params=params)
        requested.raise_for_status()
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            current = client.get(f"/api/orders/{order_id}", params=params)
            current.raise_for_status()
            artifact = current.json()["zip"]
            if artifact["status"] == "READY":
                break
            assert artifact["status"] != "FAILED", artifact.get("error")
            time.sleep(1)
        else:
            raise AssertionError("ZIP did not become ready within 60 seconds")
        assert artifact["download_url"].startswith(BASE + "/d/")
        archive = client.get(artifact["download_url"])
        archive.raise_for_status()
        with zipfile.ZipFile(BytesIO(archive.content)) as zf:
            assert len(zf.namelist()) == 2 and zf.testzip() is None
        print(f"PASS: interrupted upload, verify, upload-missing, repeat upload, bib tags, free order, originals and ZIP. Event: {slug}; order: {order_id}")
    app.processEvents()


if __name__ == "__main__":
    main()
