from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routes.orders import router as orders_router
from shared.kafka_publisher import PublishError


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


@app.exception_handler(PublishError)
def event_bus_unavailable(request: Request, exc: PublishError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(orders_router)
