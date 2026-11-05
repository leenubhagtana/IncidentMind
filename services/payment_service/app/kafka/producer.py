from shared.events import ServiceEvent
from shared.kafka_publisher import EventPublisher


publisher = EventPublisher(topic="payment-events")


def publish_event(event: ServiceEvent) -> None:
    publisher.publish(event)
