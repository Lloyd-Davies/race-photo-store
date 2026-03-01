import hmac
from typing import Generator, Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.rate_limit import enforce_rate_limit
from photostore.config import settings
from photostore.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(request: Request, x_admin_token: Optional[str] = Header(None)) -> None:
    enforce_rate_limit(request, scope="admin-auth", limit=30, window_seconds=60)
    if not settings.ADMIN_TOKEN or not x_admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")

    if not hmac.compare_digest(x_admin_token, settings.ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin token")
