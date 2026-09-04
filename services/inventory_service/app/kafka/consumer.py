import json

from confluent_kafka import Consumer

consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "inventory-service",
    "auto.offset.reset": "latest",
})


def consume_events():
    consumer.subscribe(["order-events"])

    print("Inventory consumer started...")

    try:
        while True:
            message = consumer.poll(1.0)

            if message is None:
                continue

            if message.error():
                print(f"Kafka error: {message.error()}")
                continue

            event = json.loads(message.value().decode("utf-8"))

            print("Received order event:")
            print(json.dumps(event, indent=2))

            if event["event_type"] == "order_created":
                print(
                    f"Reserving inventory for "
                    f"{event['data']['product_id']}"
                )

    finally:
        consumer.close()