
import statistics

from app.redis_client import redis_client
from app.incident_service import (
    create_incident,
    resolve_open_incident
)


BASELINE_KEY = "events:rate:history"

MIN_HISTORY = 5

Z_SCORE_THRESHOLD = 3.0


def check_event_rate(
    current_rate: int,
    event_evidence: dict
):

    # --------------------------------
    # Get historical event-rate measurements
    # --------------------------------

    history = redis_client.lrange(
        BASELINE_KEY,
        0,
        -1
    )

    history = [
        int(value)
        for value in history
    ]

    # --------------------------------
    # Learning phase
    # --------------------------------

    if len(history) < MIN_HISTORY:

        redis_client.lpush(
            BASELINE_KEY,
            current_rate
        )

        redis_client.ltrim(
            BASELINE_KEY,
            0,
            59
        )

        print(
            f"Learning normal behaviour... "
            f"{len(history) + 1}/{MIN_HISTORY}"
        )

        return False

    # --------------------------------
    # Calculate baseline
    # --------------------------------

    mean = statistics.mean(
        history
    )

    # statistics.stdev requires
    # at least two values

    if len(history) >= 2:
        std_dev = statistics.stdev(
            history
        )
    else:
        std_dev = 0

    # --------------------------------
    # Detect anomaly
    # --------------------------------

    if std_dev == 0:

        z_score = 0

        is_anomaly = (
            current_rate > mean * 2
        )

    else:

        z_score = (
            current_rate - mean
        ) / std_dev

        is_anomaly = (
            z_score > Z_SCORE_THRESHOLD
        )

    # --------------------------------
    # Save current measurement
    # --------------------------------

    redis_client.lpush(
        BASELINE_KEY,
        current_rate
    )

    redis_client.ltrim(
        BASELINE_KEY,
        0,
        59
    )

    # --------------------------------
    # Logging
    # --------------------------------

    print(
        "\nEvent Rate Analysis"
    )

    print(
        f"Current rate: "
        f"{current_rate}"
    )

    print(
        f"Baseline average: "
        f"{mean:.2f}"
    )

    print(
        f"Z-score: "
        f"{z_score:.2f}"
    )

    print(
        f"Event evidence: "
        f"{event_evidence}"
    )

    # --------------------------------
    # Create incident
    # --------------------------------

    if is_anomaly:

        reason = (
            "Event rate is significantly "
            "above the learned baseline"
        )

        print(
            "\n🚨 ANOMALY DETECTED!"
        )

        incident = create_incident(
            current_rate=current_rate,
            baseline_rate=mean,
            reason=reason,
            event_evidence=event_evidence
        )

        if incident:

            print(
                f"Active incident: "
                f"{incident.incident_id}"
            )

        return True

    # --------------------------------
    # Normal traffic
    # --------------------------------

    print(
        "Status: NORMAL"
    )

    resolved_incident = (
        resolve_open_incident()
    )

    if resolved_incident:

        print(
            f"Incident closed: "
            f"{resolved_incident.incident_id}"
        )

    return False

