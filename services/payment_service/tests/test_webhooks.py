import hashlib
import hmac
import json
import sys
import types
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    """Loads the payment service's `app` package without clashing with the
    event processor's package of the same name, and with Kafka stubbed."""

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    saved = {
        name: module for name, module in sys.modules.items()
        if name == "app" or name.startswith("app.")
    }

    for name in saved:
        del sys.modules[name]

    published = []
    stub_kafka = types.ModuleType("confluent_kafka")
    stub_kafka.Producer = lambda config: None
    monkeypatch.setitem(sys.modules, "confluent_kafka", stub_kafka)
    monkeypatch.syspath_prepend(str(SERVICE_ROOT))
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "test-secret")

    import app.routes.webhooks as webhooks

    monkeypatch.setattr(webhooks, "publish_event", published.append)

    api = FastAPI()
    api.include_router(webhooks.router)

    test_client = TestClient(api)
    test_client.published = published

    yield test_client

    for name in [
        name for name in sys.modules
        if name == "app" or name.startswith("app.")
    ]:
        del sys.modules[name]

    sys.modules.update(saved)


def failed_webhook() -> dict:
    return {
        "entity": "event",
        "account_id": "acc_1",
        "event": "payment.failed",
        "contains": ["payment"],
        "created_at": 1767000000,
        "payload": {"payment": {"entity": {
            "id": "pay_1",
            "amount": 49900,
            "currency": "INR",
            "status": "failed",
            "order_id": "order_1",
            "method": "netbanking",
            "bank": "HDFC",
            "error_code": "GATEWAY_ERROR",
            "error_source": "bank",
            "error_step": "payment_authorization",
            "error_reason": "payment_failed",
            "created_at": 1767000000,
        }}},
    }


def post(client, payload, secret="test-secret", event_id="evt_abc"):
    body = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    return client.post(
        "/webhooks/razorpay",
        content=body,
        headers={
            "X-Razorpay-Signature": signature,
            "x-razorpay-event-id": event_id,
        },
    )


def test_valid_failed_payment_is_normalised(client):
    assert post(client, failed_webhook()).status_code == 202

    event = client.published[0]

    assert event.event_id == "evt_abc"
    assert event.event_type == "payment_failed"
    assert event.data["bank"] == "HDFC"
    assert event.data["amount"] == 499.0
    assert event.data["merchant_id"] == "acc_1"


def test_bad_signature_is_rejected_and_not_published(client):
    response = post(client, failed_webhook(), secret="wrong")

    assert response.status_code == 401
    assert client.published == []


def test_tampered_body_is_rejected(client):
    body = json.dumps(failed_webhook()).encode()
    signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhooks/razorpay",
        content=body + b" ",
        headers={
            "X-Razorpay-Signature": signature,
            "x-razorpay-event-id": "evt_abc",
        },
    )

    assert response.status_code == 401


def test_unrelated_event_is_ignored(client):
    response = post(client, {"event": "refund.created", "payload": {}})

    assert response.json() == {"status": "ignored"}
    assert client.published == []


def test_missing_event_id_is_rejected(client):
    assert post(client, failed_webhook(), event_id="").status_code == 400
