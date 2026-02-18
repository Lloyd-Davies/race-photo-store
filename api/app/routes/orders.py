from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas import OrderOut
from photostore.config import settings
from photostore.models import Delivery, Order, OrderStatus

router = APIRouter(prefix="/api", tags=["orders"])


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)) -> OrderOut:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    download_url: str | None = None
    if order.status == OrderStatus.READY:
        delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
        if delivery:
            download_url = f"{settings.PUBLIC_BASE_URL}/d/{delivery.token}"

    return OrderOut(id=order.id, status=order.status, download_url=download_url)
