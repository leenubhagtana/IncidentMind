from fastapi import FastAPI

from app.routes.orders import router as orders_router


app = FastAPI(
    title="IncidentMind Order Service",
    version="1.0.0",
)


@app.get("/health")
def health_check():
    return {
        "service": "order-service",
        "status": "healthy",
    }


app.include_router(orders_router)
