import json

import app.consumer as consumer
from app.database import SessionLocal
from app.models import Event
from app.redis_client import redis_client


def raw_event(event_id="evt-1", **overrides) -> bytes:
    event = {
        "event_id": event_id,
        "event_type": "payment_failed",
        "service": "payment-service",
        "timestamp": "2026-01-15T12:00:00+00:00",
        "data": {"bank": "HDFC"},
    }
    event.update(overrides)
    return json.dumps(event).encode()


def event_count() -> int:
    with SessionLocal() as db:
        return db.query(Event).count()


def test_duplicate_event_is_stored_and_counted_once():
    dead = []
    send = lambda raw, reason: dead.append(reason)

    assert consumer.process_with_retries(raw_event(), send) == "saved"
    assert consumer.process_with_retries(raw_event(), send) == "duplicate"

    assert event_count() == 1
    assert redis_client.get("events:window:payment_failed") == "1"
    assert dead == []


def test_malformed_json_is_dead_lettered_without_retrying():
    dead = []

    outcome = consumer.process_with_retries(
        b"not json", lambda raw, reason: dead.append(reason)
    )

    assert outcome == "dead_lettered"
    assert len(dead) == 1
    assert event_count() == 0


def test_missing_fields_are_dead_lettered():
    dead = []
    payload = json.dumps({"event_id": "x"}).encode()

    outcome = consumer.process_with_retries(
        payload, lambda raw, reason: dead.append(reason)
    )

    assert outcome == "dead_lettered"
    assert "missing fields" in dead[0]


def test_bad_timestamp_is_dead_lettered_once():
    dead = []

    outcome = consumer.process_with_retries(
        raw_event(timestamp="yesterday"),
        lambda raw, reason: dead.append(reason)
    )

    assert outcome == "dead_lettered"
    assert len(dead) == 1


def test_transient_failure_recovers_on_retry(monkeypatch):
    real_save = consumer.save_event
    calls = {"count": 0}

    def flaky(event_data):
        calls["count"] += 1

        if calls["count"] == 1:
            raise ConnectionError("database restarting")

        return real_save(event_data)

    monkeypatch.setattr(consumer, "save_event", flaky)

    outcome = consumer.process_with_retries(raw_event(), lambda *_: None)

    assert outcome == "saved"
    assert calls["count"] == 2


def test_exhausted_retries_are_dead_lettered(monkeypatch):
    dead = []

    def always_down(event_data):
        raise ConnectionError("database down")

    monkeypatch.setattr(consumer, "save_event", always_down)

    outcome = consumer.process_with_retries(
        raw_event(), lambda raw, reason: dead.append(reason)
    )

    assert outcome == "dead_lettered"
    assert "retries exhausted" in dead[0]
