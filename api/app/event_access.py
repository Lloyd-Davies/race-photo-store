import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from photostore.config import settings


_PBKDF2_ITERATIONS = 240_000


def _event_access_secret() -> str:
    return settings.EVENT_ACCESS_SECRET or settings.ADMIN_TOKEN


def hash_event_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERATIONS,
    )
    digest_hex = digest.hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest_hex}"


def verify_event_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False

    try:
        algorithm, rounds_raw, salt, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(rounds_raw)
    except Exception:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        rounds,
    ).hex()

    return hmac.compare_digest(digest, digest_hex)


def create_event_access_token(event_id: int) -> tuple[str, datetime]:
    secret = _event_access_secret()
    if not secret:
        raise ValueError("EVENT_ACCESS_SECRET or ADMIN_TOKEN must be configured")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.EVENT_ACCESS_TTL_HOURS)
    payload = {
        "event_id": event_id,
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


def verify_event_access_token(token: str | None, event_id: int) -> bool:
    if not token:
        return False

    secret = _event_access_secret()
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
        token_event_id = int(payload["event_id"])
        exp = int(payload["exp"])
    except Exception:
        return False

    if token_event_id != event_id:
        return False

    return datetime.now(timezone.utc).timestamp() <= exp
