from fastapi import FastAPI

from app.routes.inventory import router as inventory_router


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


app.include_router(inventory_router)