from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Incident
from app.schemas import IncidentResponse


router = APIRouter(
    prefix="/incidents",
    tags=["Incidents"]
)


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