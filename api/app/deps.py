from typing import Generator, Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.admin_session import verify_admin_session_token
from app.rate_limit import enforce_rate_limit
from photostore.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_admin_session: Optional[str] = Header(None),
) -> None:
    enforce_rate_limit(request, scope="admin-auth", limit=30, window_seconds=60)

    bearer_token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        bearer_token = authorization[7:].strip()

    provided_token = bearer_token or x_admin_session
    if not verify_admin_session_token(provided_token, token_type="access"):
        raise HTTPException(status_code=401, detail="Invalid admin session")
