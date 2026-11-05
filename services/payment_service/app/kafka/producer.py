import json
import os

from confluent_kafka import Producer

from shared.events import ServiceEvent


producer = Producer({
    "bootstrap.servers": os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        "localhost:9092"
    )
})


def publish_event(event: ServiceEvent) -> None:
    producer.produce(
        topic="payment-events",
        key=event.event_id,
        value=json.dumps(event.model_dump(), default=str)
    )

    producer.flush()