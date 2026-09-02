from pydantic import BaseModel, Field


class OrderCreate(BaseModel):
    customer_id: str
    product_id: str
    quantity: int = Field(gt=0)
    amount: float = Field(gt=0)


class OrderResponse(BaseModel):
    order_id: str
    customer_id: str
    product_id: str
    quantity: int
    amount: float
    status: str