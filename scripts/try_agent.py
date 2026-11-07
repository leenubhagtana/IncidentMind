"""
Runs the LLM investigator on one synthetic incident and prints each step.

  python scripts/try_agent.py
  python scripts/try_agent.py card_release_regression
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "event_processor"), str(ROOT)]
load_dotenv(ROOT / ".env")

from app.investigation.agent import investigate  # noqa: E402
from evals.scenarios import build_scenarios  # noqa: E402


name = sys.argv[1] if len(sys.argv) > 1 else "bank_outage"
scenario = next(
    item for item in build_scenarios(range(1))
    if item.name == f"{name}#0"
)

client = OpenAI(
    api_key=os.environ["LLM_API_KEY"],
    base_url=os.environ["LLM_BASE_URL"],
)

result = investigate(
    client,
    os.environ["LLM_MODEL"],
    {"reason": "PAYMENT_FAILURE_SPIKE", "severity": "HIGH"},
    scenario.evidence,
)

print("Steps the agent took:")
for step in result["trace"]:
    print(" -", step["tool"], step.get("arguments", ""), step.get("problems", ""))

print("\nStatus:", result["status"])
print("Known cause:", scenario.category, scenario.scope or "")
print(json.dumps(result["findings"], indent=2))