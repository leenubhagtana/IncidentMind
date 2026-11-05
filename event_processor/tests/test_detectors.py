from app.anomaly_detector import check_event_rate
from app.config import RESOLVE_AFTER_HEALTHY_WINDOWS
from app.database import SessionLocal
from app.failure_detector import TRIGGER_EVENT, check_failure_rate
from app.incident_service import create_incident
from app.models import Incident


def incidents(status=None):
    with SessionLocal() as db:
        query = db.query(Incident)

        if status:
            query = query.filter(Incident.status == status)

        return query.all()


def test_high_failure_rate_opens_incident():
    assert check_failure_rate(
        {"payment_failed": 8, "payment_completed": 12}
    )

    incident = incidents()[0]

    assert incident.trigger_event == TRIGGER_EVENT
    assert incident.severity == "HIGH"


def test_single_bank_outage_is_detected():
    # One bank of five, failing 80% of the time, is about 16% overall.
    assert check_failure_rate(
        {"payment_failed": 27, "payment_completed": 173}
    )


def test_low_volume_never_opens_incident():
    assert not check_failure_rate(
        {"payment_failed": 2, "payment_completed": 1}
    )

    assert incidents() == []


def test_repeated_spike_keeps_one_open_incident():
    evidence = {"payment_failed": 8, "payment_completed": 12}

    check_failure_rate(evidence)
    check_failure_rate(evidence)

    assert len(incidents()) == 1


HEALTHY = {"payment_failed": 1, "payment_completed": 49}
FAILING = {"payment_failed": 8, "payment_completed": 12}


def test_consecutive_healthy_windows_resolve_incident():
    check_failure_rate(FAILING)

    for _ in range(RESOLVE_AFTER_HEALTHY_WINDOWS):
        check_failure_rate(HEALTHY)

    assert incidents()[0].status == "RESOLVED"


def test_one_lucky_healthy_window_does_not_resolve_incident():
    check_failure_rate(FAILING)
    check_failure_rate(HEALTHY)

    assert incidents()[0].status == "OPEN"


def test_failing_window_resets_healthy_streak():
    check_failure_rate(FAILING)

    for _ in range(RESOLVE_AFTER_HEALTHY_WINDOWS - 1):
        check_failure_rate(HEALTHY)

    check_failure_rate(FAILING)
    check_failure_rate(HEALTHY)

    assert incidents()[0].status == "OPEN"


def test_quiet_window_neither_resolves_nor_resets():
    check_failure_rate(FAILING)
    check_failure_rate(HEALTHY)
    check_failure_rate({"payment_completed": 2})

    assert incidents()[0].status == "OPEN"

    for _ in range(RESOLVE_AFTER_HEALTHY_WINDOWS - 1):
        check_failure_rate(HEALTHY)

    assert incidents()[0].status == "RESOLVED"


def test_traffic_incident_does_not_hide_failure_incident():
    create_incident(50, 5, "traffic", {}, [])

    check_failure_rate({"payment_failed": 8, "payment_completed": 12})

    assert len(incidents("OPEN")) == 2


def test_zero_traffic_resolves_open_traffic_incident():
    create_incident(50, 5, "traffic", {}, [])

    check_event_rate(0, {})

    assert incidents()[0].status == "RESOLVED"


def test_spike_does_not_enter_its_own_baseline():
    from app.anomaly_detector import BASELINE_KEY
    from app.redis_client import redis_client

    for value in [10, 11, 9, 10, 12, 8, 10, 11, 9, 10]:
        redis_client.lpush(BASELINE_KEY, value)

    check_event_rate(500, {"order_created": 500})

    assert "500.0" not in redis_client.lrange(BASELINE_KEY, 0, -1)
    assert "500" not in redis_client.lrange(BASELINE_KEY, 0, -1)
