import threading

from fastapi import FastAPI

from app.database import Base, engine
from app.consumer import consume_events
from app.monitor import start_monitor
from app.routes.incidents import router as incidents_router


app = FastAPI(
    title="IncidentMind Event Processor",
    description="Event processing and anomaly detection service",
    version="1.0.0"
)


# Register API routes
app.include_router(
    incidents_router
)


@app.on_event("startup")
def startup_event():

    # --------------------------------
    # Create PostgreSQL tables
    # --------------------------------

    Base.metadata.create_all(
        bind=engine
    )

    print(
        "Event Processor database ready."
    )

    # --------------------------------
    # Start Kafka Consumer
    # --------------------------------

    consumer_thread = threading.Thread(
        target=consume_events,
        daemon=True
    )

    consumer_thread.start()

    print(
        "Kafka consumer thread started."
    )

    # --------------------------------
    # Start Anomaly Monitor
    # --------------------------------

    monitor_thread = threading.Thread(
        target=start_monitor,
        daemon=True
    )

    monitor_thread.start()

    print(
        "Anomaly monitor thread started."
    )


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "event-processor"
    }