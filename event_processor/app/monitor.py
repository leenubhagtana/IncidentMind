import time

from app.redis_client import redis_client
from app.anomaly_detector import check_event_rate


CHECK_INTERVAL = 10
EVENT_WINDOW_SECONDS = 10

WINDOW_KEY_PREFIX = "events:window:"


def get_current_event_rate():

    current_time = time.time()

    window_start = (
        current_time -
        EVENT_WINDOW_SECONDS
    )

    # Remove events outside
    # the current monitoring window

    redis_client.zremrangebyscore(
        "events:timestamps",
        0,
        window_start
    )

    event_count = redis_client.zcard(
        "events:timestamps"
    )

    return event_count


def get_event_evidence():

    evidence = {}

    # Find every event-type counter
    # currently stored in Redis.

    keys = redis_client.keys(
        f"{WINDOW_KEY_PREFIX}*"
    )

    for key in keys:

        event_type = key.replace(
            WINDOW_KEY_PREFIX,
            ""
        )

        count = redis_client.get(
            key
        )

        evidence[event_type] = (
            int(count)
            if count
            else 0
        )

    return evidence


def reset_window_counters():

    keys = redis_client.keys(
        f"{WINDOW_KEY_PREFIX}*"
    )

    if keys:

        redis_client.delete(
            *keys
        )


def start_monitor():

    print(
        "Anomaly monitor started..."
    )

    print(
        f"Checking every "
        f"{CHECK_INTERVAL} seconds"
    )

    while True:

        event_rate = (
            get_current_event_rate()
        )

        event_evidence = (
            get_event_evidence()
        )

        print(
            "\nChecking event rate..."
        )

        print(
            f"Current event rate: "
            f"{event_rate}"
        )

        print(
            f"Event evidence: "
            f"{event_evidence}"
        )

        check_event_rate(
            event_rate,
            event_evidence
        )

        reset_window_counters()

        time.sleep(
            CHECK_INTERVAL
        )

