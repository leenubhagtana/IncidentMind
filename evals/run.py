"""
Scores the rule engine on synthetic incidents with known causes.

  python -m evals.run
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.investigation.rules import triage
from app.investigation.schemas import Claim, Findings, Scope
from app.investigation.verifier import verify
from evals.scenarios import build_scenarios


RESULTS_DIR = Path(__file__).parent / "results"


def is_correct(scenario, findings: dict | None) -> bool:
    if not findings or findings["category"] != scenario.category:
        return False

    if scenario.scope is None:
        return True

    scope = findings.get("scope")

    return bool(
        scope
        and scope["dimension"] == scenario.scope[0]
        and scope["value"].lower() == scenario.scope[1].lower()
    )


def run_engine(scenario):
    findings = triage(scenario.evidence)
    problems = verify(findings, scenario.evidence)

    return {
        "status": "UNVERIFIED" if problems else "VERIFIED",
        "findings": findings.model_dump(),
    }


def planted_errors(scenario) -> list[tuple[str, Findings]]:
    """False conclusions the verifier should refuse."""

    honest = triage(scenario.evidence)
    planted = []

    if honest.claims:
        wrong_number = honest.model_copy(deep=True)
        wrong_number.claims[0].reported_value += 25
        planted.append(("inflated_number", wrong_number))

    planted.append(("invented_bank", Findings(
        category="ISSUER_BANK_OUTAGE",
        scope=Scope(dimension="bank", value="FAKEBANK"),
        summary="x",
        root_cause="x",
        confidence="HIGH",
        claims=[
            Claim(
                dimension="bank",
                value="FAKEBANK",
                metric="failed",
                reported_value=50
            ),
            Claim(
                dimension="overall",
                metric="failed",
                reported_value=50
            ),
        ],
    )))

    if not scenario.evidence.deployments:
        planted.append(("blames_missing_deploy", Findings(
            category="INTERNAL_REGRESSION",
            summary="x",
            root_cause="x",
            confidence="MEDIUM",
            claims=honest.claims,
        )))

    return planted


def verifier_catch_rate(scenarios) -> dict:
    caught = total = 0
    by_type = defaultdict(lambda: [0, 0])

    for scenario in scenarios:
        for name, findings in planted_errors(scenario):
            rejected = bool(verify(findings, scenario.evidence))
            caught += rejected
            total += 1
            by_type[name][0] += rejected
            by_type[name][1] += 1

    return {
        "caught": caught,
        "total": total,
        "by_type": {
            name: {"caught": values[0], "total": values[1]}
            for name, values in by_type.items()
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()

    scenarios = build_scenarios(range(args.seeds))
    rows = []

    for scenario in scenarios:
        outcome = run_engine(scenario)
        rows.append({
            "scenario": scenario.name,
            "hard": scenario.hard,
            "expected": scenario.category,
            "actual": outcome["findings"]["category"],
            "status": outcome["status"],
            "correct": is_correct(scenario, outcome["findings"]),
        })

    def accuracy(selected):
        return {
            "correct": sum(row["correct"] for row in selected),
            "total": len(selected),
        }

    report = {
        "engine": "rules",
        "data": "synthetic",
        "all": accuracy(rows),
        "standard": accuracy([row for row in rows if not row["hard"]]),
        "hard": accuracy([row for row in rows if row["hard"]]),
        "verified_but_wrong": sum(
            row["status"] == "VERIFIED" and not row["correct"]
            for row in rows
        ),
        "verifier_on_planted_errors": verifier_catch_rate(scenarios),
        "rows": rows,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "rules.json").write_text(
        json.dumps(report, indent=2)
    )

    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))

    for row in rows:
        if not row["correct"]:
            print(f"MISS {row['scenario']}: {row['actual']} ({row['status']})")


if __name__ == "__main__":
    main()
