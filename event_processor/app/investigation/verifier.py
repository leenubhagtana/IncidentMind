"""
Checks an investigation against the events before anyone sees it.

These rules are independent of whatever produced the conclusion, so a wrong
number or an unsupported conclusion is caught before it reaches anyone.
"""
from app.investigation.evidence import (
    Evidence,
    concentration,
    failure_onset,
    metric_value,
)
from app.investigation.schemas import Findings


RATE_TOLERANCE = 0.01

CATEGORY_DIMENSIONS = {
    "ISSUER_BANK_OUTAGE": "bank",
    "PAYMENT_METHOD_OUTAGE": "method",
    "MERCHANT_CONFIGURATION": "merchant_id",
}


def verify(findings: Findings, evidence: Evidence) -> list[str]:
    """Returns every problem found. An empty list means verified."""

    problems = []

    for claim in findings.claims:
        actual = metric_value(
            evidence,
            claim.dimension,
            claim.value,
            claim.metric
        )

        if actual is None:
            problems.append(
                f"Claim references data that does not exist: "
                f"{claim.dimension}={claim.value!r} {claim.metric}."
            )
            continue

        is_count = claim.metric in ("attempts", "failed")
        tolerance = 0 if is_count else RATE_TOLERANCE

        if abs(actual - claim.reported_value) > tolerance:
            problems.append(
                f"Wrong number for {claim.dimension}={claim.value!r} "
                f"{claim.metric}: reported {claim.reported_value}, "
                f"actual {actual}."
            )

    if findings.category == "INCONCLUSIVE":
        return problems

    if not findings.claims:
        problems.append("A conclusion needs at least one numeric claim.")

    if findings.confidence == "HIGH" and len(findings.claims) < 2:
        problems.append("HIGH confidence needs at least two claims.")

    required_dimension = CATEGORY_DIMENSIONS.get(findings.category)

    if required_dimension:
        problems.extend(
            check_scope(findings, evidence, required_dimension)
        )

    if findings.category == "INTERNAL_REGRESSION":
        problems.extend(check_regression(evidence))

    if findings.category == "CUSTOMER_SIDE_DECLINES":
        problems.extend(check_customer_side(evidence))

    return problems


def check_scope(
    findings: Findings,
    evidence: Evidence,
    required_dimension: str
) -> list[str]:
    scope = findings.scope

    if scope is None or scope.dimension != required_dimension:
        return [
            f"{findings.category} must be scoped to a "
            f"{required_dimension}."
        ]

    top = concentration(evidence, required_dimension)

    if top is None or top["value"].lower() != scope.value.lower():
        return [
            f"Failures are not concentrated in "
            f"{required_dimension}={scope.value!r}."
        ]

    return []


def check_regression(evidence: Evidence) -> list[str]:
    onset = failure_onset(evidence)

    if onset is None:
        return ["No failure onset found to link to a deployment."]

    preceding = [
        deployment for deployment in evidence.deployments
        if deployment["timestamp"] <= onset
    ]

    if not preceding:
        return [
            "INTERNAL_REGRESSION needs a deployment before failures "
            f"began at {onset.isoformat()}, and none exists."
        ]

    return []


def check_customer_side(evidence: Evidence) -> list[str]:
    top = concentration(evidence, "error_source")

    if top is None or top["value"] != "customer":
        return ["Failures are not concentrated in customer errors."]

    return []
