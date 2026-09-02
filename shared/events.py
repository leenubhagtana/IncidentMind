from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class ServiceEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    service: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    data: dict