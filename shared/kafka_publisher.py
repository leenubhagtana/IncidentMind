import json
import os
import threading

from confluent_kafka import KafkaException, Producer

from shared.events import ServiceEvent


DELIVERY_TIMEOUT_SECONDS = float(os.getenv("KAFKA_DELIVERY_TIMEOUT_SECONDS", "5"))


class PublishError(Exception):
    """The event could not be confirmed by Kafka in time."""


class EventPublisher:
    """
    One producer per process, shared by all request threads.

    Calling flush() per request made every request wait for every other
    request's messages, with no upper bound. Instead a background thread
    serves delivery callbacks and each request waits only for its own
    message, up to DELIVERY_TIMEOUT_SECONDS.
    """

    def __init__(self, topic: str):
        self.topic = topic
        self.producer = Producer({
            "bootstrap.servers": os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS",
                "localhost:9092"
            ),
            "linger.ms": 5,
            "message.timeout.ms": int(DELIVERY_TIMEOUT_SECONDS * 1000),
            "enable.idempotence": True,
        })
        threading.Thread(target=self._poll_forever, daemon=True).start()

    def _poll_forever(self) -> None:
        while True:
            self.producer.poll(0.1)

    def publish(self, event: ServiceEvent) -> None:
        delivered = threading.Event()
        outcome: dict = {}

        def on_delivery(err, msg):
            outcome["error"] = err
            delivered.set()

        try:
            self.producer.produce(
                topic=self.topic,
                key=event.event_id,
                value=json.dumps(event.model_dump(), default=str),
                on_delivery=on_delivery,
            )
        except (BufferError, KafkaException) as exc:
            raise PublishError(f"Kafka rejected event: {exc}") from exc

        if not delivered.wait(DELIVERY_TIMEOUT_SECONDS + 1):
            raise PublishError("Timed out waiting for Kafka delivery")

        if outcome["error"] is not None:
            print(f"❌ Kafka delivery failed: {outcome['error']}")
            raise PublishError(f"Kafka delivery failed: {outcome['error']}")
