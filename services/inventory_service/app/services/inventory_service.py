import uuid

from app.schemas.inventory import InventoryReservation


def reserve_inventory(reservation: InventoryReservation) -> dict:
    return {
        "reservation_id": f"res_{uuid.uuid4().hex[:8]}",
        "product_id": reservation.product_id,
        "quantity": reservation.quantity,
        "status": "reserved"
    }