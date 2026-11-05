from datetime import timedelta

from app.investigation.evidence import concentration, failure_onset, group_rows
from app.investigation.rules import triage
from app.investigation.schemas import Claim, Findings, Scope
from app.investigation.verifier import verify
from evals.scenarios import build_scenarios


def scenario(name):
    return next(
        item for item in build_scenarios(range(1))
        if item.name == f"{name}#0"
    )


def base_findings(**overrides):
    values = {
        "category": "INCONCLUSIVE",
        "summary": "s",
        "root_cause": "r",
        "confidence": "LOW",
    }
    values.update(overrides)
    return Findings(**values)


def test_breakdown_counts_add_up():
    evidence = scenario("bank_outage").evidence

    rows = group_rows(evidence, "bank")

    assert sum(row["attempts"] for row in rows) == 300
    assert abs(sum(row["share_of_failures"] for row in rows) - 1) < 0.01


def test_concentration_finds_failing_bank():
    top = concentration(scenario("bank_outage").evidence, "bank")

    assert top["value"] == "HDFC"


def test_concentration_ignores_even_spread():
    assert concentration(scenario("customer_declines").evidence, "bank") is None


def test_onset_is_not_fooled_by_stray_declines():
    for seed in range(5):
        item = next(
            found for found in build_scenarios(range(seed + 1))
            if found.name == f"deploy_regression#{seed}"
        )

        onset = failure_onset(item.evidence)
        deployed_at = item.evidence.deployments[0]["timestamp"]

        assert onset >= deployed_at - timedelta(seconds=20)


def test_verifier_accepts_honest_findings():
    evidence = scenario("bank_outage").evidence

    assert verify(triage(evidence), evidence) == []


def test_verifier_rejects_wrong_number():
    evidence = scenario("bank_outage").evidence
    findings = triage(evidence)
    findings.claims[0].reported_value += 10

    assert any("Wrong number" in p for p in verify(findings, evidence))


def test_verifier_rejects_invented_value():
    evidence = scenario("bank_outage").evidence
    findings = base_findings(
        claims=[Claim(
            dimension="bank",
            value="NOPE",
            metric="failed",
            reported_value=1
        )]
    )

    assert any("does not exist" in p for p in verify(findings, evidence))


def test_verifier_rejects_deploy_after_onset():
    evidence = scenario("outage_with_later_deploy").evidence
    findings = base_findings(
        category="INTERNAL_REGRESSION",
        confidence="MEDIUM",
        claims=triage(evidence).claims,
    )

    assert any("deployment" in p for p in verify(findings, evidence))


def test_verifier_rejects_bank_without_concentration():
    evidence = scenario("customer_declines").evidence
    findings = base_findings(
        category="ISSUER_BANK_OUTAGE",
        scope=Scope(dimension="bank", value="HDFC"),
        confidence="MEDIUM",
        claims=[Claim(
            dimension="overall",
            metric="attempts",
            reported_value=300
        )],
    )

    assert any("not concentrated" in p for p in verify(findings, evidence))
