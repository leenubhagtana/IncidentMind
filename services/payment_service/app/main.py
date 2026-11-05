from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routes.payments import router as payment_router
from app.routes.webhooks import router as webhook_router
from shared.kafka_publisher import PublishError


app = FastAPI(
    title="IncidentMind Payment Service",
    version="1.0.0"
)


@app.get("/health")
def health_check():
    return {
        "service": "payment-service",
        "status": "healthy"
    }


@app.exception_handler(PublishError)
def event_bus_unavailable(request: Request, exc: PublishError):
    # A 5xx also makes MyPay retry the webhook later.
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(payment_router)
app.include_router(webhook_router)