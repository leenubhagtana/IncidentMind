import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import (
    DEAD_LETTER_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    MAX_PROCESSING_ATTEMPTS,
)
from app.database import SessionLocal
from app.event_store import store_recent_event
from app.models import Event
from app.redis_client import redis_client


WINDOW_KEY_PREFIX = "events:window:"
REQUIRED_FIELDS = ("event_id", "event_type", "service", "timestamp", "data")


class PermanentEventError(ValueError):
    """The message can never succeed, so retrying it is pointless."""


def parse_message(raw: bytes) -> dict:
    try:
        event_data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PermanentEventError(f"invalid JSON: {exc}") from exc

    if not isinstance(event_data, dict):
        raise PermanentEventError("event is not a JSON object")

    missing = [
        field for field in REQUIRED_FIELDS
        if field not in event_data
    ]

    if missing:
        raise PermanentEventError(f"missing fields: {missing}")

    return event_data


def to_utc_naive(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise PermanentEventError(f"bad timestamp: {value}") from exc

    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed


def save_event(event_data: dict) -> bool:
    """
    Store one event exactly once. Returns False for a duplicate.

    Kafka delivers at least once and Razorpay retries webhooks, so the same
    event_id can arrive twice. Counters update only after a new row commits,
    which stops duplicates from inflating the anomaly detector's numbers.
    """

    db: Session = SessionLocal()

    try:
        if db.get(Event, event_data["event_id"]):
            return False

        event = Event(
            event_id=event_data["event_id"],
            event_type=event_data["event_type"],
            service=event_data["service"],
            timestamp=to_utc_naive(event_data["timestamp"]),
            data=event_data["data"],
        )

        db.add(event)
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    update_counters(event_data)

    return True


def update_counters(event_data: dict) -> None:
    event_type = event_data["event_type"]

    redis_client.incr("events:total")
    redis_client.incr(f"events:type:{event_type}")
    redis_client.incr(f"{WINDOW_KEY_PREFIX}{event_type}")
    redis_client.set("events:last", json.dumps(event_data, default=str))

    store_recent_event(event_data)

    now = datetime.now(timezone.utc).timestamp()
    redis_client.zadd(
        "events:timestamps",
        {f"event:{event_data['event_id']}": now}
    )


def process_with_retries(raw: bytes, send_to_dead_letter) -> str:
    """
    Returns "saved", "duplicate" or "dead_lettered".

    Bad data goes straight to the dead-letter topic. Transient failures such
    as a Postgres restart are retried first. Either way one bad message
    cannot block the partition behind it.
    """

    try:
        event_data = parse_message(raw)
    except PermanentEventError as exc:
        send_to_dead_letter(raw, str(exc))
        return "dead_lettered"

    last_error = None

    for _ in range(MAX_PROCESSING_ATTEMPTS):
        try:
            return "saved" if save_event(event_data) else "duplicate"
        except PermanentEventError as exc:
            send_to_dead_letter(raw, str(exc))
            return "dead_lettered"
        except Exception as exc:
            last_error = exc

    send_to_dead_letter(raw, f"retries exhausted: {last_error}")
    return "dead_lettered"


def consume_events():
    from confluent_kafka import Consumer, Producer

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": "event-processor",
        "auto.offset.reset": "earliest",
        # Commit only after the event is stored or dead-lettered.
        "enable.auto.commit": False,
    })

    dead_letter_producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS
    })

    def send_to_dead_letter(raw: bytes, reason: str) -> None:
        print(f"Dead-lettering message: {reason}")
        dead_letter_producer.produce(
            DEAD_LETTER_TOPIC,
            value=raw,
            headers={"reason": reason}
        )
        dead_letter_producer.flush()

    consumer.subscribe(["order-events", "payment-events"])

    print("Event Processor started...")

    try:
        while True:
            message = consumer.poll(1.0)

            if message is None:
                continue

            if message.error():
                print(f"Kafka error: {message.error()}")
                continue

            outcome = process_with_retries(
                message.value(),
                send_to_dead_letter
            )

            consumer.commit(message=message)

            print(f"Event {outcome}")

    finally:
        consumer.close()
