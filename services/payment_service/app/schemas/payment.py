from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    order_id: str
    amount: float = Field(gt=0)
    currency: str = "INR"


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    amount: float
    currency: str
    status: str