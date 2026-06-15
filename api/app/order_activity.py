from typing import Any

from sqlalchemy.orm import Session

from photostore.models import OrderActivity


def record_order_activity(
    db: Session,
    *,
    order_id: int | None,
    action: str,
    message: str,
    actor: str = "system",
    metadata: dict[str, Any] | None = None,
) -> OrderActivity:
    activity = OrderActivity(
        order_id=order_id,
        actor=actor,
        action=action,
        message=message,
        metadata_json=metadata,
    )
    db.add(activity)
    return activity
