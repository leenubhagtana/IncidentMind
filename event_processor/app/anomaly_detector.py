import statistics

from app.redis_client import redis_client
from app.event_store import get_recent_events
from app.incident_service import (
    create_incident,
    resolve_open_incident,
)


BASELINE_KEY = "events:rate:history"

MIN_HISTORY = 10
MAX_HISTORY = 60

Z_SCORE_THRESHOLD = 3.0

# Don't consider tiny traffic volumes anomalous.
MIN_EVENT_RATE = 5


def classify_incident(event_evidence: dict) -> str:
    """
    Classify an anomaly based on clearly dominant
    event types.
    """

    if not event_evidence:
        return "GENERAL_TRAFFIC_ANOMALY"

    order_count = event_evidence.get(
        "order_created",
        0
    )

    payment_count = event_evidence.get(
        "payment_completed",
        0
    )

    total_events = order_count + payment_count

    if total_events == 0:
        return "GENERAL_TRAFFIC_ANOMALY"

    if order_count >= payment_count * 2:
        return "ORDER_SPIKE"

    if payment_count >= order_count * 2:
        return "PAYMENT_SPIKE"

    if order_count > 0 and payment_count > 0:
        return "MULTI_SERVICE_ANOMALY"

    return "GENERAL_TRAFFIC_ANOMALY"


def load_history():
    values = redis_client.lrange(
        BASELINE_KEY,
        0,
        MAX_HISTORY - 1
    )

    return [
        float(value)
        for value in values
    ]


def save_history(current_rate: float):
    redis_client.lpush(
        BASELINE_KEY,
        current_rate
    )

    redis_client.ltrim(
        BASELINE_KEY,
        0,
        MAX_HISTORY - 1
    )


def check_event_rate(
    current_rate: int,
    event_evidence: dict
):

    history = load_history()

    # -----------------------------------------
    # Ignore empty measurements
    # -----------------------------------------

    if current_rate <= 0:

        print(
            "No events detected in current window."
        )

        return False

    # -----------------------------------------
    # Learn baseline
    # -----------------------------------------

    if len(history) < MIN_HISTORY:

        save_history(current_rate)

        print(
            f"Learning normal behaviour... "
            f"{len(history) + 1}/{MIN_HISTORY}"
        )

        print(
            f"Current rate: {current_rate}"
        )

        return False

    # -----------------------------------------
    # Calculate baseline
    # -----------------------------------------

    mean = statistics.mean(history)

    if len(history) >= 2:

        std_dev = statistics.stdev(history)

    else:

        std_dev = 0

    # -----------------------------------------
    # Protect against bad baseline
    # -----------------------------------------

    if mean <= 0:

        print(
            "Baseline is invalid. "
            "Skipping anomaly detection."
        )

        save_history(current_rate)

        return False

    # -----------------------------------------
    # Calculate z-score
    # -----------------------------------------

    if std_dev > 0:

        z_score = (
            (current_rate - mean)
            / std_dev
        )

    else:

        z_score = 0

    # -----------------------------------------
    # Determine anomaly
    # -----------------------------------------

    is_anomaly = False

    if current_rate >= MIN_EVENT_RATE:

        if std_dev > 0:

            is_anomaly = (
                z_score >= Z_SCORE_THRESHOLD
            )

        else:

            is_anomaly = (
                current_rate >= mean * 3
            )

    # -----------------------------------------
    # Save current measurement
    # -----------------------------------------

    save_history(current_rate)

    # -----------------------------------------
    # Print analysis
    # -----------------------------------------

    print("")
    print("===================================")
    print("Event Rate Analysis")
    print("===================================")

    print(
        f"Current rate: {current_rate}"
    )

    print(
        f"Baseline average: {mean:.2f}"
    )

    print(
        f"Standard deviation: {std_dev:.2f}"
    )

    print(
        f"Z-score: {z_score:.2f}"
    )

    print(
        f"Event evidence: {event_evidence}"
    )

    print(
        f"History samples: {len(history)}"
    )

    # -----------------------------------------
    # NORMAL
    # -----------------------------------------

    if not is_anomaly:

        print("Status: NORMAL")

        resolved_incident = (
            resolve_open_incident()
        )

        if resolved_incident:

            print(
                f"Incident closed: "
                f"{resolved_incident.incident_id}"
            )

        return False

    # -----------------------------------------
    # ANOMALY
    # -----------------------------------------

    print("")
    print("🚨 ANOMALY DETECTED!")

    incident_type = classify_incident(
        event_evidence
    )

    print(
        f"Incident classification: "
        f"{incident_type}"
    )

    recent_events = get_recent_events(
        limit=20
    )

    reason = (
        f"{incident_type}: event rate is "
        f"significantly above the learned baseline"
    )

    incident = create_incident(
        current_rate=current_rate,
        baseline_rate=mean,
        reason=reason,
        event_evidence=event_evidence,
        recent_events=recent_events
    )

    if incident:

        print(
            f"Active incident: "
            f"{incident.incident_id}"
        )

        print(
            f"Severity: "
            f"{incident.severity}"
        )

    return True