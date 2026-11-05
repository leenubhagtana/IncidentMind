import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app import config
from app.investigation.evidence import Evidence
from app.investigation.rules import triage
from app.investigation.verifier import verify
from app.models import Event, Incident, Investigation


PAYMENT_EVENTS = ("payment_completed", "payment_failed")
DEPLOYMENT_EVENT = "service_deployed"


def as_dict(event: Event) -> dict:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp,
        "data": event.data,
    }


def load_evidence(db: Session, incident: Incident) -> Evidence:
    detected_at = incident.detected_at

    incident_start = detected_at - timedelta(
        seconds=config.INCIDENT_LOOKBACK_SECONDS
    )
    baseline_start = incident_start - timedelta(
        seconds=config.BASELINE_LOOKBACK_SECONDS
    )

    rows = (
        db.query(Event)
        .filter(
            Event.timestamp >= baseline_start,
            Event.timestamp <= detected_at,
        )
        .all()
    )

    payments = [
        as_dict(row) for row in rows
        if row.event_type in PAYMENT_EVENTS
    ]

    return Evidence(
        detected_at=detected_at,
        incident_events=[
            event for event in payments
            if event["timestamp"] >= incident_start
        ],
        baseline_events=[
            event for event in payments
            if event["timestamp"] < incident_start
        ],
        deployments=[
            {"timestamp": row.timestamp, **row.data}
            for row in rows
            if row.event_type == DEPLOYMENT_EVENT
        ],
    )


def run_rules(evidence: Evidence) -> dict:
    findings = triage(evidence)
    problems = verify(findings, evidence)

    return {
        "status": "UNVERIFIED" if problems else "VERIFIED",
        "findings": findings.model_dump(),
        "verification_problems": problems,
        "trace": [],
    }


def run_investigation(db: Session, incident: Incident) -> Investigation:
    evidence = load_evidence(db, incident)

    outcome = run_rules(evidence)

    investigation = Investigation(
        investigation_id=f"INV-{uuid.uuid4().hex[:8].upper()}",
        incident_id=incident.incident_id,
        engine="rules",
        status=outcome["status"],
        result={
            "findings": outcome["findings"],
            "verification_problems": outcome["verification_problems"],
        },
        trace=outcome["trace"],
    )

    db.add(investigation)
    db.commit()
    db.refresh(investigation)

    return investigation
