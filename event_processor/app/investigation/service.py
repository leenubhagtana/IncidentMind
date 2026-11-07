import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app import config
from app.investigation.agent import investigate
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


def llm_is_configured() -> bool:
    return bool(config.LLM_API_KEY and config.LLM_MODEL)


def llm_client():
    from openai import OpenAI

    return OpenAI(
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
        # Fail fast: a slow model must not leave the on-call engineer waiting.
        timeout=60,
        max_retries=2,
    )


def run_llm(incident: Incident, evidence: Evidence) -> dict:
    incident_summary = {
        "incident_id": incident.incident_id,
        "severity": incident.severity,
        "reason": incident.reason,
        "affected_service": incident.affected_service,
        "detected_at": incident.detected_at,
    }

    return investigate(
        llm_client(),
        config.LLM_MODEL,
        incident_summary,
        evidence,
        config.LLM_MAX_STEPS,
    )


def choose_engine(incident: Incident, evidence: Evidence) -> tuple[str, dict]:
    """
    Use the LLM when it is configured and produces an answer.
    Otherwise fall back to the rule engine, so an investigation
    always comes back even if the LLM is down or out of quota.
    """

    if not llm_is_configured():
        return "rules", run_rules(evidence)

    try:
        outcome = run_llm(incident, evidence)
    except Exception as exc:
        print(f"LLM investigation failed, using rules: {exc}")
        return "rules (llm unavailable)", run_rules(evidence)

    if outcome["status"] == "FAILED":
        return "rules (llm gave no answer)", run_rules(evidence)

    return f"llm:{config.LLM_MODEL}", outcome


def run_investigation(db: Session, incident: Incident) -> Investigation:
    evidence = load_evidence(db, incident)

    engine, outcome = choose_engine(incident, evidence)

    investigation = Investigation(
        investigation_id=f"INV-{uuid.uuid4().hex[:8].upper()}",
        incident_id=incident.incident_id,
        engine=engine,
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