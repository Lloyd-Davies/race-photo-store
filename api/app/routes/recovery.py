"""Read-only historical preview and explicit, authenticated recovery selection."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.deps import get_db
from app.routes.admin import require_admin
from photostore.config import settings
from photostore.models import Communication, CommunicationStatus, DeliveryZipStatus, Order, OrderActivity, OrderStatus, RecoveryActivation, RecoveryJob
from photostore.recovery import ensure_job, exclusion

router = APIRouter(prefix="/api/admin", tags=["recovery"], dependencies=[Depends(require_admin)])


def steps(order, db):
    result = []
    missing_email = (settings.EMAIL_ENABLED and order.email and not db.query(Communication.id)
                     .filter_by(order_id=order.id, dedupe_key=f"download_ready:{order.id}").first())
    if order.status != OrderStatus.READY or not order.delivery or missing_email:
        result.append(("payment", order.id, "Verify payment and repair delivery"))
    for comm in db.query(Communication).filter_by(order_id=order.id).all():
        if comm.status in {CommunicationStatus.QUEUED, CommunicationStatus.FAILED, CommunicationStatus.DEFERRED}:
            result.append(("email", comm.id, "Retry unconfirmed email; duplicates are possible"))
    if order.delivery and order.delivery.zip_status in {DeliveryZipStatus.BUILDING, DeliveryZipStatus.FAILED}:
        result.append(("zip", order.id, "Resume customer-requested ZIP"))
    if order.stripe_pricing_status in {"QUEUED", "FAILED"}:
        result.append(("pricing", order.id, "Synchronize payment details"))
    return result


@router.get("/recovery/preview")
def preview(db: Session = Depends(get_db), after_id: int = Query(0, ge=0)):
    activation = db.get(RecoveryActivation, 1)
    orders = db.query(Order).filter(Order.created_at < activation.activated_at,
        Order.id > after_id).order_by(Order.id).limit(100).all()
    return {"candidates": [{"order_id": o.id, "excluded_reason": exclusion(o, db),
        "steps": [s[2] for s in steps(o, db)]} for o in orders if steps(o, db)],
        "next_after_id": orders[-1].id if len(orders) == 100 else None}


@router.get("/orders/{order_id}/recovery")
def details(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    jobs = db.query(RecoveryJob).filter_by(order_id=order_id).order_by(RecoveryJob.id).all()
    def error(job):
        if job.error:
            return job.error
        if job.kind == "email":
            comm = db.get(Communication, job.target_id)
            return comm.error_message if comm else "Communication missing"
        if job.kind == "zip" and order.delivery:
            return order.delivery.zip_error
        return None
    return {"excluded_reason": exclusion(order, db), "steps": [s[2] for s in steps(order, db)],
        "jobs": [{"kind": j.kind, "status": j.status, "attempts": j.attempts,
                  "last_attempt_at": j.last_attempt_at, "next_attempt_at": j.next_attempt_at,
                  "error": error(j)} for j in jobs]}


@router.post("/orders/{order_id}/recovery")
def retry(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter_by(id=order_id).with_for_update().first()
    if not order:
        raise HTTPException(404, "Order not found")
    reason = exclusion(order, db)
    if reason:
        raise HTTPException(409, reason)
    selected = steps(order, db)
    for kind, target_id, _ in selected:
        ensure_job(db, order.id, kind, target_id, restart=True, approved=True)
    # Selection also authorizes later dependent work for a historical order.
    if selected:
        ensure_job(db, order.id, "payment", order.id, approved=True)
        db.add(OrderActivity(order_id=order.id, actor="admin", action="RECOVERY_SELECTED",
            message="Recovery explicitly selected; access limits preserved"))
    db.commit()
    return details(order_id, db)
