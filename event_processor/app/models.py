from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
)

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

class Investigation(Base):
    """One investigation run. The trace keeps every tool call for audit."""

    __tablename__ = "investigations"

    investigation_id = Column(
        String,
        primary_key=True
    )

    incident_id = Column(
        String,
        ForeignKey("incidents.incident_id"),
        nullable=False,
        index=True
    )

    engine = Column(
        String,
        nullable=False
    )

    status = Column(
        String,
        nullable=False
    )

    result = Column(
        JSON,
        nullable=False
    )

    trace = Column(
        JSON,
        nullable=False,
        default=list
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )


class ActionDecision(Base):
    """A human decision on a proposed action. Nothing here executes it."""

    __tablename__ = "action_decisions"

    decision_id = Column(
        String,
        primary_key=True
    )

    investigation_id = Column(
        String,
        ForeignKey("investigations.investigation_id"),
        nullable=False,
        index=True
    )

    action_index = Column(
        Integer,
        nullable=False
    )

    decision = Column(
        String,
        nullable=False
    )

    decided_by = Column(
        String,
        nullable=False
    )

    decided_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow
    )
