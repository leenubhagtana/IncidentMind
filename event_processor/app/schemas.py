from datetime import datetime

from pydantic import BaseModel


class IncidentResponse(BaseModel):

    incident_id: str

    status: str

    severity: str

    reason: str

    affected_service: str

    trigger_event: str

    evidence: dict

    current_rate: float

    baseline_rate: float

    detected_at: datetime

    class Config:
        from_attributes = True