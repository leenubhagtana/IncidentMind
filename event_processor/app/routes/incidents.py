import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Event, Incident
from app.schemas import IncidentResponse


router = APIRouter(
    prefix="/incidents",
    tags=["Incidents"]
)


class DeploymentRecord(BaseModel):
    service: str
    version: str


def get_db():

    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()


@router.get(
    "",
    response_model=list[IncidentResponse]
)
def get_incidents(
    status: str | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(Incident)

    if status:

        query = query.filter(
            Incident.status == status.upper()
        )

    incidents = (
        query
        .order_by(
            Incident.detected_at.desc()
        )
        .all()
    )

    return incidents


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse
)
def get_incident(
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

    return incident

@router.post("/deployments", status_code=201)
def record_deployment(
    deployment: DeploymentRecord,
    db: Session = Depends(get_db)
):
    """Called by CI so the investigator can compare deploys with failures."""

    event = Event(
        event_id=f"deploy-{uuid.uuid4().hex}",
        event_type="service_deployed",
        service=deployment.service,
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        data=deployment.model_dump(),
    )

    db.add(event)
    db.commit()

    return {"event_id": event.event_id}
