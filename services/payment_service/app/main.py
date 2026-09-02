from fastapi import FastAPI

from app.routes.payments import router as payment_router


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


app.include_router(payment_router)