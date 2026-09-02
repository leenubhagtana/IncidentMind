import uuid

from app.schemas.payment import PaymentCreate


def process_payment(payment: PaymentCreate) -> dict:
    return {
        "payment_id": f"pay_{uuid.uuid4().hex[:8]}",
        "order_id": payment.order_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "status": "completed"
    }