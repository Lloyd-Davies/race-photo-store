from collections import deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request


_LOCK = Lock()
_BUCKETS: dict[str, deque[float]] = {}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _bucket_key(request: Request, scope: str, suffix: str | None = None) -> str:
    ip = _client_ip(request)
    if suffix:
        return f"{scope}:{ip}:{suffix}"
    return f"{scope}:{ip}"


def enforce_rate_limit(
    request: Request,
    scope: str,
    limit: int,
    window_seconds: int,
    suffix: str | None = None,
) -> None:
    key = _bucket_key(request, scope, suffix)
    now = monotonic()
    window_start = now - window_seconds

    with _LOCK:
        bucket = _BUCKETS.setdefault(key, deque())
        while bucket and bucket[0] <= window_start:
            bucket.popleft()

        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests. Please try again shortly.")

        bucket.append(now)


def reset_rate_limits() -> None:
    with _LOCK:
        _BUCKETS.clear()
