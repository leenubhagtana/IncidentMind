import json

from confluent_kafka import Consumer

from app.kafka.producer import publish_event
from shared.events import ServiceEvent


consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "payment-service",
    "auto.offset.reset": "latest",
})


def consume_events():
    consumer.subscribe(["order-events"])

    print("Payment consumer started...")

    try:
        while True:
            message = consumer.poll(1.0)

            if message is None:
                continue

            if message.error():
                print(f"Kafka error: {message.error()}")
                continue

            event = json.loads(message.value().decode("utf-8"))

            print("Received order event")

            payment_event = ServiceEvent(
                event_type="payment_completed",
                service="payment-service",
                data={
                    "order_id": event["data"]["order_id"],
                    "amount": event["data"]["amount"],
                    "status": "completed"
                }
            )

            publish_event(payment_event)

            print("Published payment_completed")

    finally:
        consumer.close()