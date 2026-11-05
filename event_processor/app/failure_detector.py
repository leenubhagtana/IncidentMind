"""
Detects payment failure spikes.

The existing z-score detector watches event volume. A bank outage can leave
volume flat while most payments fail, so the failure rate is tracked as its
own signal.
"""
import statistics

from app.config import (
    FAILURE_RATE_THRESHOLD,
    MIN_PAYMENT_ATTEMPTS,
    RESOLVE_AFTER_HEALTHY_WINDOWS,
)
from app.event_store import get_recent_events
from app.incident_service import create_incident, resolve_open_incident
from app.redis_client import redis_client


TRIGGER_EVENT = "payment_failure_spike"
HISTORY_KEY = "payments:failure_rate:history"
HEALTHY_STREAK_KEY = "payments:failure_rate:healthy_streak"
MAX_HISTORY = 60


def failure_rate(event_evidence: dict) -> tuple[int, float]:
    failed = event_evidence.get("payment_failed", 0)
    completed = event_evidence.get("payment_completed", 0)
    attempts = failed + completed

    if attempts == 0:
        return 0, 0.0

    return attempts, failed / attempts


def severity_for(rate: float) -> str:
    if rate >= 0.5:
        return "CRITICAL"

    if rate >= 0.3:
        return "HIGH"

    return "MEDIUM"


def healthy_baseline() -> float:
    values = redis_client.lrange(HISTORY_KEY, 0, MAX_HISTORY - 1)

    if not values:
        return 0.0

    return statistics.mean(float(value) for value in values)


def check_failure_rate(event_evidence: dict) -> bool:
    attempts, rate = failure_rate(event_evidence)

    if attempts < MIN_PAYMENT_ATTEMPTS:
        # Too little traffic to judge either way: neither a failure
        # nor evidence of recovery, so the healthy streak is kept.
        return False

    if rate < FAILURE_RATE_THRESHOLD:
        # Only healthy windows teach the baseline, so an outage
        # cannot redefine itself as normal.
        redis_client.lpush(HISTORY_KEY, rate)
        redis_client.ltrim(HISTORY_KEY, 0, MAX_HISTORY - 1)

        healthy_streak = redis_client.incr(HEALTHY_STREAK_KEY)

        if healthy_streak >= RESOLVE_AFTER_HEALTHY_WINDOWS:
            resolve_open_incident(TRIGGER_EVENT)

        return False

    redis_client.set(HEALTHY_STREAK_KEY, 0)

    create_incident(
        current_rate=round(rate * 100, 2),
        baseline_rate=round(healthy_baseline() * 100, 2),
        reason=(
            f"PAYMENT_FAILURE_SPIKE: {rate:.0%} of {attempts} "
            f"payment attempts failed in the window"
        ),
        event_evidence=event_evidence,
        recent_events=get_recent_events(limit=20),
        affected_service="payment-service",
        trigger_event=TRIGGER_EVENT,
        severity=severity_for(rate),
    )

    return True
