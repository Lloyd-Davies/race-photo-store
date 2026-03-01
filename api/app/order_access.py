import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from photostore.config import settings


def _order_access_secret() -> str:
    return settings.ADMIN_SESSION_SECRET or settings.ADMIN_TOKEN


def create_order_access_token(order_id: int) -> tuple[str, datetime]:
    secret = _order_access_secret()
    if not secret:
        raise ValueError("EVENT_ACCESS_SECRET or ADMIN_TOKEN must be configured")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.ORDER_ACCESS_TTL_HOURS)
    payload = {
        "order_id": order_id,
        "exp": int(expires_at.timestamp()),
    }

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")

    signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return f"{payload_b64}.{signature}", expires_at


def verify_order_access_token(token: str | None, order_id: int) -> bool:
    if not token:
        return False

    secret = _order_access_secret()
    if not secret:
        return False

    try:
        payload_b64, sent_signature = token.split(".", 1)
    except ValueError:
        return False

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, sent_signature):
        return False

    try:
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(payload_raw.decode("utf-8"))
        token_order_id = int(payload["order_id"])
        exp = int(payload["exp"])
    except Exception:
        return False

    if token_order_id != order_id:
        return False

    return datetime.now(timezone.utc).timestamp() <= exp
