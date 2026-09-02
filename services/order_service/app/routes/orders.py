from fastapi import APIRouter

from app.schemas.order import OrderCreate, OrderResponse
from app.services.order_service import create_order


router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


@router.post("", response_model=OrderResponse)
def create_new_order(order: OrderCreate):
    return create_order(order)