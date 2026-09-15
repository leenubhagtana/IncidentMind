from datetime import datetime

from sqlalchemy import Column, String, DateTime, JSON, Float

from app.database import Base


class Event(Base):
    __tablename__ = "events"

    event_id = Column(
        String,
        primary_key=True
    )

    event_type = Column(
        String,
        nullable=False
    )

    service = Column(
        String,
        nullable=False
    )

    timestamp = Column(
        DateTime,
        nullable=False
    )

    data = Column(
        JSON,
        nullable=False
    )

class Incident(Base):
    __tablename__ = "incidents"

    incident_id = Column(
        String,
        primary_key=True
    )

    status = Column(
        String,
        nullable=False,
        default="OPEN"
    )

    severity = Column(
        String,
        nullable=False
    )

    reason = Column(
        String,
        nullable=False
    )

    affected_service = Column(
        String,
        nullable=False,
        default="unknown"
    )

    trigger_event = Column(
        String,
        nullable=False,
        default="unknown"
    )

    evidence = Column(
        JSON,
        nullable=False,
        default=dict
    )

    current_rate = Column(
        Float,
        nullable=False
    )

    baseline_rate = Column(
        Float,
        nullable=False
    )

    detected_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )