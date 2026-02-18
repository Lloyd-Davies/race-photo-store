from fastapi import APIRouter

router = APIRouter()


@router.get("/api/healthz", tags=["health"])
def healthz() -> dict:
    return {"ok": True}
