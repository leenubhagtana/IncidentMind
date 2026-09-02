import uuid

from app.kafka.producer import publish_event
from app.schemas.order import OrderCreate
from shared.events import ServiceEvent


def create_order(order: OrderCreate) -> dict:
    result = {
        "order_id": f"ord_{uuid.uuid4().hex[:8]}",
        "customer_id": order.customer_id,
        "product_id": order.product_id,
        "quantity": order.quantity,
        "amount": order.amount,
        "status": "created"
    }

    publish_event(
        ServiceEvent(
            event_type="order_created",
            service="order-service",
            data=result,
        )
    )

    return result
