import json

from confluent_kafka import Consumer
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Event

from app.redis_client import redis_client


consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "event-processor",
    "auto.offset.reset": "earliest",
})


def consume_events():
    consumer.subscribe([
        "order-events",
        "payment-events"
    ])

    print("Event Processor started...")

    try:
        while True:
            message = consumer.poll(1.0)

            if message is None:
                continue

            if message.error():
                print(f"Kafka error: {message.error()}")
                continue

            event = json.loads(
                message.value().decode("utf-8")
            )

            print(
                f"Received: {event['event_type']} "
                f"from {event['service']}"
            )

            save_event(event)

    finally:
        consumer.close()


def save_event(event_data: dict):
    db: Session = SessionLocal()

    try:
        event = Event(
            event_id=event_data["event_id"],
            event_type=event_data["event_type"],
            service=event_data["service"],
            timestamp=event_data["timestamp"],
            data=event_data["data"],
        )

        db.add(event)
        db.commit()

        redis_client.incr("events:total")
        redis_client.incr(
            f"events:type:{event_data['event_type']}"
        )
        redis_client.set(
            "events:last",
            json.dumps(event_data, default=str)
        )

        print(
            f"Saved to PostgreSQL: "
            f"{event.event_type}"
        )

    except Exception as exc:
        db.rollback()
        print(f"Database error: {exc}")

    finally:
        db.close()