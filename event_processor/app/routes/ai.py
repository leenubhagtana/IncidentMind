from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Incident
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