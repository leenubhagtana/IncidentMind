"""Deterministic triage of a payment failure incident."""
from app.investigation.evidence import (
    Evidence,
    concentration,
    failure_onset,
    summarize,
)
from app.investigation.schemas import Claim, Findings, ProposedAction, Scope


CHECKS = (
    ("error_source", "customer", "CUSTOMER_SIDE_DECLINES"),
    ("merchant_id", None, "MERCHANT_CONFIGURATION"),
    ("bank", None, "ISSUER_BANK_OUTAGE"),
    ("method", None, "PAYMENT_METHOD_OUTAGE"),
)


def overall_claims(evidence: Evidence) -> list[Claim]:
    overall = summarize(evidence.incident_events)

    return [
        Claim(
            dimension="overall",
            metric="failed",
            reported_value=overall["failed"]
        ),
        Claim(
            dimension="overall",
            metric="failure_rate",
            reported_value=overall["failure_rate"]
        ),
    ]


def triage(evidence: Evidence) -> Findings:
    for dimension, required_value, category in CHECKS:
        top = concentration(evidence, dimension)

        if top is None:
            continue

        if required_value and top["value"] != required_value:
            continue

        scope = None

        if dimension != "error_source":
            scope = Scope(dimension=dimension, value=top["value"])

        return Findings(
            category=category,
            scope=scope,
            summary=(
                f"{top['share_of_failures']:.0%} of failures share "
                f"{dimension}={top['value']}."
            ),
            root_cause=(
                f"Failures are concentrated in {dimension}={top['value']}. "
                f"Rule engine output: this shows where, not why."
            ),
            confidence="MEDIUM",
            claims=overall_claims(evidence) + [
                Claim(
                    dimension=dimension,
                    value=top["value"],
                    metric="share_of_failures",
                    reported_value=top["share_of_failures"]
                )
            ],
            proposed_actions=[
                ProposedAction(
                    action=f"Review failures for {dimension}={top['value']}.",
                    risk="LOW"
                )
            ],
        )

    onset = failure_onset(evidence)

    if onset and any(
        deployment["timestamp"] <= onset
        for deployment in evidence.deployments
    ):
        return Findings(
            category="INTERNAL_REGRESSION",
            summary="Failures are spread widely and began after a deployment.",
            root_cause="Timing points to the most recent deployment.",
            confidence="MEDIUM",
            claims=overall_claims(evidence),
            proposed_actions=[
                ProposedAction(
                    action="Review the most recent deployment.",
                    risk="LOW"
                )
            ],
        )

    return Findings(
        category="INCONCLUSIVE",
        summary="No single cause stands out in the event data.",
        root_cause="The available evidence does not identify a cause.",
        confidence="LOW",
        claims=overall_claims(evidence),
    )
