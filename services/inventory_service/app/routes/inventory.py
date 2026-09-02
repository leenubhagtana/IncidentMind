from fastapi import APIRouter

from app.schemas.inventory import (
    InventoryReservation,
    InventoryResponse,
)
from app.services.inventory_service import reserve_inventory


router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"]
)


@router.post("/reserve", response_model=InventoryResponse)
def reserve(reservation: InventoryReservation):
    return reserve_inventory(reservation)