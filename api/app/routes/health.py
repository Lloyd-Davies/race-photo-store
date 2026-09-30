from fastapi import APIRouter
from photostore.build_info import read_build_info
from photostore.celery_app import celery_app

router = APIRouter()


@router.get("/api/healthz", tags=["health"])
def healthz() -> dict:
    return {"ok": True}


@router.get('/internal/build-info', include_in_schema=False)
def build_info() -> dict:
    # No credentials, settings or worker hostnames leave this interface.
    workers = []
    try:
        replies = celery_app.control.broadcast('photostore_build_info', reply=True, timeout=2)
        for reply in replies or []:
            for identity in reply.values():
                if isinstance(identity, dict) and identity.get('component') == 'worker':
                    workers.append({'component': 'worker', 'revision': identity.get('revision', 'unknown')})
    except Exception:
        # Runtime inspection is optional; database protection must remain available.
        pass
    return {'api': read_build_info('api'), 'workers': workers}
