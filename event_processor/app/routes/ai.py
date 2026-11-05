import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.failure_detector import TRIGGER_EVENT
from app.investigation.service import run_investigation
from app.models import ActionDecision, Incident, Investigation
from app.ai_analyst import analyze_incident


router = APIRouter(
    prefix="/ai",
    tags=["AI Analyst"]
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@router.post("/incidents/{incident_id}/analyze")
def analyze_incident_endpoint(
    incident_id: str,
    db: Session = Depends(get_db)
):
    incident = (
        db.query(Incident)
        .filter(
            Incident.incident_id == incident_id
        )
        .first()
    )

    if not incident:
        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    # Failure spikes get a full investigation. Traffic anomalies
    # keep the existing rule-based analyst.
    if incident.trigger_event == TRIGGER_EVENT:
        investigation = run_investigation(db, incident)

        return {
            "incident_id": incident.incident_id,
            "investigation_id": investigation.investigation_id,
            "engine": investigation.engine,
            "status": investigation.status,
            **investigation.result,
            "trace": investigation.trace,
        }

    incident_data = {
        "incident_id": incident.incident_id,
        "status": incident.status,
        "severity": incident.severity,
        "reason": incident.reason,
        "affected_service": incident.affected_service,
        "trigger_event": incident.trigger_event,
        "evidence": incident.evidence,
        "current_rate": incident.current_rate,
        "baseline_rate": incident.baseline_rate,
        "detected_at": incident.detected_at,
    }

    analysis = analyze_incident(
        incident_data
    )

    return {
        "incident_id": incident.incident_id,
        "analysis": analysis
    }

class ActionDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    decided_by: str


@router.post("/investigations/{investigation_id}/actions/{action_index}")
def decide_action(
    investigation_id: str,
    action_index: int,
    request: ActionDecisionRequest,
    db: Session = Depends(get_db)
):
    """Records a human decision. No action is executed from this service."""

    investigation = db.get(Investigation, investigation_id)

    if not investigation:
        raise HTTPException(
            status_code=404,
            detail="Investigation not found"
        )

    findings = investigation.result.get("findings") or {}
    actions = findings.get("proposed_actions", [])

    if not 0 <= action_index < len(actions):
        raise HTTPException(
            status_code=404,
            detail="Action not found"
        )

    if request.decision == "APPROVED" and investigation.status != "VERIFIED":
        raise HTTPException(
            status_code=409,
            detail="Actions from an unverified investigation cannot be approved"
        )

    decision = ActionDecision(
        decision_id=f"DEC-{uuid.uuid4().hex[:8].upper()}",
        investigation_id=investigation_id,
        action_index=action_index,
        decision=request.decision,
        decided_by=request.decided_by,
    )

    db.add(decision)
    db.commit()

    return {
        "decision_id": decision.decision_id,
        "action": actions[action_index],
        "decision": decision.decision,
    }
