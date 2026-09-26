
import json
import time

from confluent_kafka import Consumer
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Event
from app.redis_client import redis_client
from app.event_store import store_recent_event

WINDOW_KEY_PREFIX = "events:window:"

RECENT_EVENTS_KEY = "events:recent"

MAX_RECENT_EVENTS = 100


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

    print(
        "Event Processor started..."
    )

    try:

        while True:

            message = consumer.poll(
                1.0
            )

            if message is None:
                continue

            if message.error():

                print(
                    f"Kafka error: "
                    f"{message.error()}"
                )

                continue

            event_data = json.loads(
                message.value().decode(
                    "utf-8"
                )
            )

            print(
                f"Received: "
                f"{event_data['event_type']} "
                f"from "
                f"{event_data['service']}"
            )

            save_event(
                event_data
            )

    finally:

        consumer.close()


def track_event_rate():

    current_time = time.time()

    event_key = (
        f"event:"
        f"{current_time}:"
        f"{time.time_ns()}"
    )

    redis_client.zadd(
        "events:timestamps",
        {
            event_key:
                current_time
        }
    )

    return redis_client.zcard(
        "events:timestamps"
    )


def save_event(
    event_data: dict
):

    db: Session = SessionLocal()

    try:

        # --------------------------------
        # PostgreSQL
        # --------------------------------

        event = Event(

            event_id=
                event_data["event_id"],

            event_type=
                event_data["event_type"],

            service=
                event_data["service"],

            timestamp=
                event_data["timestamp"],

            data=
                event_data["data"]
        )

        db.add(
            event
        )

        db.commit()

        # --------------------------------
        # Redis: total events
        # --------------------------------

        redis_client.incr(
            "events:total"
        )

        # --------------------------------
        # Redis: lifetime event counter
        # --------------------------------

        redis_client.incr(
            f"events:type:"
            f"{event_data['event_type']}"
        )

        # --------------------------------
        # Redis: current window counter
        # --------------------------------

        redis_client.incr(
            f"{WINDOW_KEY_PREFIX}"
            f"{event_data['event_type']}"
        )

        # --------------------------------
        # Redis: latest event
        # --------------------------------

        redis_client.set(
            "events:last",
            json.dumps(
                event_data,
                default=str
            )
        )

        # --------------------------------
        # Redis: recent events
        # --------------------------------

        store_recent_event(
            event_data
        )

        # --------------------------------
        # Redis: event timestamp
        # --------------------------------

        event_count = (
            track_event_rate()
        )

        # --------------------------------
        # Logging
        # --------------------------------

        print(
            f"Saved to PostgreSQL: "
            f"{event.event_type}"
        )

        print(
            f"Events currently tracked: "
            f"{event_count}"
        )

    except Exception as exc:

        db.rollback()

        print(
            f"Event processing error: "
            f"{exc}"
        )

    finally:

        db.close()

