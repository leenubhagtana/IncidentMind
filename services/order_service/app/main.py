from fastapi import FastAPI

app = FastAPI(
    title="IncidentMind Order Service",
    version="1.0.0"
)


@app.get("/health")
def health_check():
    return {
        "service": "order-service",
        "status": "healthy"
    }


@app.post("/orders")
def create_order():
    return {
        "order_id": "order_123",
        "status": "created"
    }