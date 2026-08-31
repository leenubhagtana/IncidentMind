from fastapi import FastAPI

app = FastAPI(
    title="IncidentMind Inventory Service",
    version="1.0.0"
)


@app.get("/health")
def health_check():
    return {
        "service": "inventory-service",
        "status": "healthy"
    }


@app.post("/inventory/reserve")
def reserve_inventory():
    return {
        "reservation_id": "res_123",
        "status": "reserved"
    }