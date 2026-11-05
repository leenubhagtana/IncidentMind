"""
Read-only analysis of payment events.

The rule engine and the verifier both use this code, so conclusions are
checked against numbers computed directly from the events.
"""
from dataclasses import dataclass, field
from datetime import datetime


DIMENSIONS = (
    "bank",
    "method",
    "merchant_id",
    "error_code",
    "error_source",
)


@dataclass
class Evidence:
    detected_at: datetime
    incident_events: list[dict]
    baseline_events: list[dict]
    deployments: list[dict] = field(default_factory=list)


def is_failure(event: dict) -> bool:
    return event["event_type"] == "payment_failed"


def summarize(events: list[dict]) -> dict:
    attempts = len(events)
    failed = sum(1 for event in events if is_failure(event))

    return {
        "attempts": attempts,
        "failed": failed,
        "failure_rate": round(failed / attempts, 4) if attempts else 0.0,
    }


def group_rows(evidence: Evidence, dimension: str) -> list[dict]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unknown dimension: {dimension}")

    incident_failures = sum(
        1 for event in evidence.incident_events if is_failure(event)
    )

    groups: dict[str, list[dict]] = {}
    baseline_groups: dict[str, list[dict]] = {}

    for event in evidence.incident_events:
        key = str(event["data"].get(dimension) or "unknown")
        groups.setdefault(key, []).append(event)

    for event in evidence.baseline_events:
        key = str(event["data"].get(dimension) or "unknown")
        baseline_groups.setdefault(key, []).append(event)

    rows = []

    for value, events in groups.items():
        current = summarize(events)
        baseline = summarize(baseline_groups.get(value, []))

        rows.append({
            "value": value,
            **current,
            "baseline_failure_rate": baseline["failure_rate"],
            "share_of_failures": round(
                current["failed"] / incident_failures, 4
            ) if incident_failures else 0.0,
        })

    return sorted(rows, key=lambda row: row["failed"], reverse=True)


def metric_value(
    evidence: Evidence,
    dimension: str,
    value: str,
    metric: str
) -> float | None:
    """The trusted value of one metric, or None if it does not exist."""

    if dimension == "overall":
        row = summarize(evidence.incident_events)
        row["baseline_failure_rate"] = summarize(
            evidence.baseline_events
        )["failure_rate"]
    else:
        row = next(
            (
                candidate for candidate in group_rows(evidence, dimension)
                if candidate["value"].lower() == str(value).lower()
            ),
            None
        )

    if row is None or metric not in row:
        return None

    return row[metric]


def failure_onset(evidence: Evidence) -> datetime | None:
    """
    When the failure rate changed, found with a CUSUM change-point.

    Taking the first failure would not work: customer declines happen all
    the time, so a stray one just before a deployment would make the failures
    look older than the deployment.
    """

    events = sorted(
        evidence.incident_events,
        key=lambda event: event["timestamp"]
    )

    flags = [is_failure(event) for event in events]

    if sum(flags) < 3:
        return None

    mean = sum(flags) / len(flags)
    running = lowest = 0.0
    change_index = 0

    for index, failed in enumerate(flags):
        running += failed - mean

        if running < lowest:
            lowest = running
            change_index = index + 1

    for event, failed in zip(events[change_index:], flags[change_index:]):
        if failed:
            return event["timestamp"]

    return None


def concentration(evidence: Evidence, dimension: str) -> dict | None:
    """
    The value that explains most failures, if there is one.

    High share alone is not enough: HDFC can hold 60% of failures simply by
    holding 60% of traffic. The value must also fail far more than the rest.
    """

    rows = group_rows(evidence, dimension)

    if not rows or rows[0]["failed"] == 0:
        return None

    top = rows[0]
    others = [row for row in rows if row["value"] != top["value"]]
    other_attempts = sum(row["attempts"] for row in others)
    other_failed = sum(row["failed"] for row in others)
    other_rate = other_failed / other_attempts if other_attempts else 0.0

    if top["value"] == "unknown" or top["share_of_failures"] < 0.6:
        return None

    if others and top["failure_rate"] < max(other_rate * 2, 0.15):
        return None

    return {**top, "other_failure_rate": round(other_rate, 4)}
