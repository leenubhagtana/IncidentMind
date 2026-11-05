
import uuid

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Incident


DEFAULT_TRIGGER = "event_rate_anomaly"

def calculate_severity(
    current_rate: float,
    baseline_rate: float
):

    if baseline_rate <= 0:

        if current_rate >= 20:
            return "CRITICAL"

        if current_rate >= 10:
            return "HIGH"

        return "MEDIUM"

    ratio = (
        current_rate /
        baseline_rate
    )

    if ratio >= 5:
        return "CRITICAL"

    if ratio >= 3:
        return "HIGH"

    return "MEDIUM"


def get_open_incident(
    db: Session,
    trigger_event: str = DEFAULT_TRIGGER
):

    # One open incident per signal, so a traffic spike
    # cannot hide a payment failure that starts during it.
    return (
        db.query(Incident)
        .filter(
            Incident.status == "OPEN",
            Incident.trigger_event == trigger_event
        )
        .order_by(
            Incident.detected_at.desc()
        )
        .first()
    )


def resolve_open_incident(
    trigger_event: str = DEFAULT_TRIGGER
):

    db: Session = SessionLocal()

    try:

        open_incident = (
            get_open_incident(db, trigger_event)
        )

        if not open_incident:
            return None

        open_incident.status = "RESOLVED"

        db.commit()

        db.refresh(
            open_incident
        )

        print(
            "\n=============================="
        )

        print(
            "✅ INCIDENT RESOLVED"
        )

        print(
            "=============================="
        )

        print(
            f"Incident ID: "
            f"{open_incident.incident_id}"
        )

        print(
            f"Status: "
            f"{open_incident.status}"
        )

        print(
            "Traffic returned to normal."
        )

        print(
            "==============================\n"
        )

        return open_incident

    except Exception as exc:

        db.rollback()

        print(
            f"Incident resolution error: "
            f"{exc}"
        )

        return None

    finally:

        db.close()


def create_incident(
    current_rate: float,
    baseline_rate: float,
    reason: str,
    event_evidence: dict,
    recent_events: list,
    affected_service: str = "event-processor",
    trigger_event: str = DEFAULT_TRIGGER,
    severity: str | None = None
):

    db: Session = SessionLocal()

    try:

        # --------------------------------
        # Prevent duplicate incidents
        # --------------------------------

        open_incident = (
            get_open_incident(db, trigger_event)
        )

        if open_incident:

            print(
                "\nExisting OPEN incident found."
            )

            print(
                f"Incident ID: "
                f"{open_incident.incident_id}"
            )

            print(
                "No duplicate incident created."
            )

            return open_incident

        # --------------------------------
        # Generate incident ID
        # --------------------------------

        incident_id = (
            f"INC-"
            f"{uuid.uuid4().hex[:8].upper()}"
        )

        # --------------------------------
        # Severity
        # --------------------------------

        severity = severity or calculate_severity(
            current_rate,
            baseline_rate
        )

        # --------------------------------
        # Rate multiplier
        # --------------------------------

        if baseline_rate > 0:

            rate_multiplier = round(
                current_rate /
                baseline_rate,
                2
            )

        else:

            rate_multiplier = None

        # --------------------------------
        # Evidence
        # --------------------------------

        evidence = {

            "current_event_rate":
                current_rate,

            "baseline_event_rate":
                baseline_rate,

            "rate_multiplier":
                rate_multiplier,

            "detection_reason":
                reason,

            "event_counts":
                event_evidence,

            "recent_events":
                recent_events
        }

        # --------------------------------
        # Create incident
        # --------------------------------

        incident = Incident(

            incident_id=
                incident_id,

            status=
                "OPEN",

            severity=
                severity,

            reason=
                reason,

            affected_service=
                affected_service,

            trigger_event=
                trigger_event,

            evidence=
                evidence,

            current_rate=
                current_rate,

            baseline_rate=
                baseline_rate
        )

        db.add(
            incident
        )

        db.commit()

        db.refresh(
            incident
        )

        # --------------------------------
        # Logging
        # --------------------------------

        print(
            "\n=============================="
        )

        print(
            "🚨 INCIDENT CREATED"
        )

        print(
            "=============================="
        )

        print(
            f"Incident ID: "
            f"{incident.incident_id}"
        )

        print(
            f"Status: "
            f"{incident.status}"
        )

        print(
            f"Severity: "
            f"{incident.severity}"
        )

        print(
            f"Affected Service: "
            f"{incident.affected_service}"
        )

        print(
            f"Trigger Event: "
            f"{incident.trigger_event}"
        )

        print(
            f"Reason: "
            f"{incident.reason}"
        )

        print(
            f"Current Rate: "
            f"{incident.current_rate}"
        )

        print(
            f"Baseline Rate: "
            f"{incident.baseline_rate}"
        )

        print(
            f"Event Counts: "
            f"{event_evidence}"
        )

        print(
            f"Recent Events: "
            f"{len(recent_events)}"
        )

        print(
            "==============================\n"
        )

        return incident

    except Exception as exc:

        db.rollback()

        print(
            f"Incident creation error: "
            f"{exc}"
        )

        return None

    finally:

        db.close()

