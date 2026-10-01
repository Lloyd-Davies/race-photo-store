from celery import Celery

from .config import settings

celery_app = Celery(
    "photostore",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,   # one task at a time per worker process
    task_acks_late=True,            # ack only after the task completes
)

celery_app.conf.beat_schedule = {
    "recover-orders-five-minutely": {
        "task": "tasks.recover_orders.recover_orders", "schedule": 300.0,
    },
}
if settings.ZIP_CLEANUP_ENABLED:
    celery_app.conf.beat_schedule.update({
        "cleanup-expired-zips-hourly": {
            "task": "tasks.cleanup_expired_zips.cleanup_expired_zips",
            "schedule": 3600.0,
        },
    })
