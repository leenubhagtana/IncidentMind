import json


def analyze_incident(incident: dict) -> dict:
    """
    Local AI-style incident analyst.

    Important:
    This does NOT claim to know the true root cause.
    It separates observed evidence from inference.
    """

    evidence = incident.get("evidence", {})

    event_counts = evidence.get(
        "event_counts",
        {}
    )

    current_rate = float(
        incident.get("current_rate", 0)
    )

    baseline_rate = float(
        incident.get("baseline_rate", 0)
    )

    severity = incident.get(
        "severity",
        "UNKNOWN"
    )

    reason = incident.get(
        "reason",
        ""
    )

    affected_service = incident.get(
        "affected_service",
        "unknown"
    )

    # -----------------------------------------
    # Event counts
    # -----------------------------------------

    order_count = int(
        event_counts.get(
            "order_created",
            0
        )
    )

    payment_count = int(
        event_counts.get(
            "payment_completed",
            0
        )
    )

    total_events = order_count + payment_count

    # -----------------------------------------
    # Calculate multiplier
    # -----------------------------------------

    if baseline_rate > 0:
        rate_multiplier = (
            current_rate / baseline_rate
        )
    else:
        rate_multiplier = 0

    # -----------------------------------------
    # Observed evidence
    # -----------------------------------------

    observed_evidence = [
        f"Current event rate: {current_rate:.2f}",
        f"Baseline event rate: {baseline_rate:.2f}",
        f"Observed rate multiplier: {rate_multiplier:.2f}x",
        f"Order events in window: {order_count}",
        f"Payment events in window: {payment_count}",
        f"Total observed events: {total_events}",
        f"Affected service recorded by detector: {affected_service}",
        f"Detector reason: {reason}"
    ]

    # -----------------------------------------
    # Root-cause reasoning
    # -----------------------------------------

    # We need a meaningful difference before
    # claiming one event type dominates.

    if total_events == 0:

        root_cause = (
            "Insufficient event evidence to identify "
            "a likely cause."
        )

        confidence = "LOW"

        impact = (
            "An anomaly was recorded, but there is "
            "insufficient event evidence to determine "
            "its operational impact."
        )

        recommendations = [
            "Collect additional events.",
            "Inspect service logs around the detection time.",
            "Review Kafka consumer and producer metrics."
        ]

    elif order_count >= payment_count * 2:

        root_cause = (
            "The event window contains substantially "
            "more order events than payment events. "
            "This is consistent with elevated order "
            "traffic, but the available evidence does "
            "not establish the underlying cause."
        )

        confidence = "MEDIUM"

        impact = (
            "The order service and downstream consumers "
            "may experience increased processing load."
        )

        recommendations = [
            "Inspect order-service request volume.",
            "Check Kafka order-events consumer lag.",
            "Review order-service logs around the detection time.",
            "Check whether the increase is associated with "
            "a deployment or external traffic source."
        ]

    elif payment_count >= order_count * 2:

        root_cause = (
            "The event window contains substantially "
            "more payment events than order events. "
            "This is consistent with elevated payment "
            "activity, but the available evidence does "
            "not establish the underlying cause."
        )

        confidence = "MEDIUM"

        impact = (
            "The payment service and downstream systems "
            "may experience increased processing load."
        )

        recommendations = [
            "Inspect payment-service logs.",
            "Check Kafka payment-events consumer lag.",
            "Investigate payment retry behaviour.",
            "Check for duplicate payment requests."
        ]

    else:

        root_cause = (
            "The anomaly is associated with increased "
            "overall event activity. Order and payment "
            "events are relatively balanced, so the "
            "available evidence does not identify a "
            "specific service as the root cause."
        )

        confidence = "LOW"

        impact = (
            "Multiple services may be experiencing "
            "increased event-processing load."
        )

        recommendations = [
            "Inspect Order, Payment and Inventory service logs.",
            "Check Kafka producer and consumer activity.",
            "Review recent deployments or configuration changes.",
            "Collect additional event-level evidence before "
            "assigning a specific root cause."
        ]

    # -----------------------------------------
    # Summary
    # -----------------------------------------

    summary = (
        f"{severity} event-rate anomaly detected. "
        f"The observed rate was {current_rate:.2f}, "
        f"compared with a baseline of "
        f"{baseline_rate:.2f}."
    )

    # -----------------------------------------
    # Final structured analysis
    # -----------------------------------------

    return {
        "summary": summary,

        "root_cause": root_cause,

        "impact": impact,

        "confidence": confidence,

        "evidence": observed_evidence,

        "recommended_actions": recommendations
    }