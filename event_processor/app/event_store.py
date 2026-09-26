
import json

from app.redis_client import redis_client


RECENT_EVENTS_KEY = "events:recent"

MAX_RECENT_EVENTS = 100


def store_recent_event(
    event_data: dict
):

    redis_client.lpush(
        RECENT_EVENTS_KEY,
        json.dumps(
            event_data,
            default=str
        )
    )

    redis_client.ltrim(
        RECENT_EVENTS_KEY,
        0,
        MAX_RECENT_EVENTS - 1
    )


def get_recent_events(
    limit: int = 20
):

    events = redis_client.lrange(
        RECENT_EVENTS_KEY,
        0,
        limit - 1
    )

    return [
        json.loads(event)
        for event in events
    ]

