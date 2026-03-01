import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

from photostore.config import settings


def _admin_session_secret() -> str:
    return settings.ADMIN_SESSION_SECRET or settings.ADMIN_TOKEN


def _encode(payload: dict) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(
        _admin_session_secret().encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def _decode_and_verify(token: str | None) -> dict | None:
    if not token:
        return None

    secret = _admin_session_secret()
    if not secret:
        return None

    try:
        payload_b64, sent_signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, sent_signature):
        return None

    try:
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(payload_raw.decode("utf-8"))
        payload_type = str(payload["typ"])
        payload_subject = str(payload["sub"])
        payload_exp = int(payload["exp"])
    except Exception:
        return None

    if payload_subject != "admin":
        return None
    if datetime.now(timezone.utc).timestamp() > payload_exp:
        return None

    return {"typ": payload_type, "sub": payload_subject, "exp": payload_exp}


def create_admin_session_tokens() -> tuple[str, datetime, str, datetime]:
    if not _admin_session_secret():
        raise ValueError("ADMIN_SESSION_SECRET, EVENT_ACCESS_SECRET, or ADMIN_TOKEN must be configured")

    now = datetime.now(timezone.utc)
    access_expires_at = now + timedelta(minutes=settings.ADMIN_SESSION_TTL_MINUTES)
    refresh_expires_at = now + timedelta(hours=settings.ADMIN_REFRESH_TTL_HOURS)

    access_token = _encode(
        {
            "typ": "access",
            "sub": "admin",
            "exp": int(access_expires_at.timestamp()),
        }
    )
    refresh_token = _encode(
        {
            "typ": "refresh",
            "sub": "admin",
            "exp": int(refresh_expires_at.timestamp()),
        }
    )

    return access_token, access_expires_at, refresh_token, refresh_expires_at


def verify_admin_session_token(token: str | None, token_type: str) -> bool:
    payload = _decode_and_verify(token)
    if not payload:
        return False
    return payload.get("typ") == token_type
