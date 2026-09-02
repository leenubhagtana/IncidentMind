from fastapi import APIRouter

from app.schemas.payment import PaymentCreate, PaymentResponse
from app.services.payment_service import process_payment


router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)


@router.post("", response_model=PaymentResponse)
def create_payment(payment: PaymentCreate):
    return process_payment(payment)


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: str):
    return {
        "payment_id": payment_id,
        "order_id": "order_001",
        "amount": 499.99,
        "currency": "INR",
        "status": "completed"
    }