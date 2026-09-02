from pydantic import BaseModel, Field


class InventoryReservation(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class InventoryResponse(BaseModel):
    reservation_id: str
    product_id: str
    quantity: int
    status: str