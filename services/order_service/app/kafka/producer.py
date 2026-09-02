import json

from confluent_kafka import Producer

from shared.events import ServiceEvent


producer = Producer({
    "bootstrap.servers": "localhost:9092"
})


def delivery_report(err, msg):
    if err is not None:
        print(f"❌ Kafka delivery failed: {err}")
    else:
        print(
            f"✅ Kafka event delivered: "
            f"topic={msg.topic()} partition={msg.partition()}"
        )


def publish_event(event: ServiceEvent) -> None:
    producer.produce(
        topic="order-events",
        key=event.event_id,
        value=json.dumps(
            event.model_dump(),
            default=str
        ),
        callback=delivery_report
    )

    producer.flush()