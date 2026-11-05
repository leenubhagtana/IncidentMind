"""API flow over a real database session, with the background threads off."""
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Event, Incident
from app.routes.ai import router as ai_router
from app.routes.incidents import router as incidents_router
from evals.scenarios import DETECTED_AT, build_scenarios


api = FastAPI()
api.include_router(ai_router)
api.include_router(incidents_router)
client = TestClient(api)


def seed_incident() -> str:
    evidence = next(
        item for item in build_scenarios(range(1))
        if item.name == "bank_outage#0"
    ).evidence

    with SessionLocal() as db:
        for event in evidence.incident_events + evidence.baseline_events:
            db.add(Event(
                event_id=event["event_id"],
                event_type=event["event_type"],
                service="payment-service",
                timestamp=event["timestamp"],
                data=event["data"],
            ))

        db.add(Incident(
            incident_id="INC-TEST",
            severity="HIGH",
            reason="PAYMENT_FAILURE_SPIKE",
            affected_service="payment-service",
            trigger_event="payment_failure_spike",
            evidence={},
            current_rate=20,
            baseline_rate=3,
            detected_at=DETECTED_AT + timedelta(seconds=1),
        ))
        db.commit()

    return "INC-TEST"


def test_investigation_runs_rule_engine():
    response = client.post(f"/ai/incidents/{seed_incident()}/analyze")

    body = response.json()

    assert response.status_code == 200
    assert body["engine"] == "rules"
    assert body["status"] == "VERIFIED"
    assert body["findings"]["category"] == "ISSUER_BANK_OUTAGE"
    assert body["findings"]["scope"]["value"] == "HDFC"


def test_human_decision_is_recorded():
    investigation = client.post(
        f"/ai/incidents/{seed_incident()}/analyze"
    ).json()

    response = client.post(
        f"/ai/investigations/{investigation['investigation_id']}/actions/0",
        json={"decision": "APPROVED", "decided_by": "on-call"},
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "APPROVED"


def test_unknown_action_is_404():
    investigation = client.post(
        f"/ai/incidents/{seed_incident()}/analyze"
    ).json()

    response = client.post(
        f"/ai/investigations/{investigation['investigation_id']}/actions/99",
        json={"decision": "APPROVED", "decided_by": "on-call"},
    )

    assert response.status_code == 404


def test_deployment_is_recorded():
    response = client.post(
        "/incidents/deployments",
        json={"service": "payment-service", "version": "2.0.0"},
    )

    assert response.status_code == 201
