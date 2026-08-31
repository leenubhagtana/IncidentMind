from fastapi import FastAPI

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


@app.post("/payments")
def create_payment():
    return {
        "payment_id": "pay_123",
        "status": "completed"
    }