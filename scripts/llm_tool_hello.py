"""Which engine runs, and what happens when the LLM fails."""
from app import config
from app.investigation import service
from evals.scenarios import build_scenarios


EVIDENCE = next(
    item for item in build_scenarios(range(1))
    if item.name == "bank_outage#0"
).evidence


class FakeIncident:
    incident_id = "INC-1"
    severity = "HIGH"
    reason = "PAYMENT_FAILURE_SPIKE"
    affected_service = "payment-service"
    detected_at = EVIDENCE.detected_at


def configure_llm(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")


def test_no_key_uses_rules(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")

    engine, outcome = service.choose_engine(FakeIncident(), EVIDENCE)

    assert engine == "rules"
    assert outcome["status"] == "VERIFIED"


def test_llm_answer_is_used(monkeypatch):
    configure_llm(monkeypatch)
    monkeypatch.setattr(service, "run_llm", lambda incident, evidence: {
        "status": "VERIFIED", "findings": {}, "verification_problems": [], "trace": [],
    })

    engine, _ = service.choose_engine(FakeIncident(), EVIDENCE)

    assert engine == "llm:test-model"


def test_llm_error_falls_back_to_rules(monkeypatch):
    configure_llm(monkeypatch)

    def quota_exceeded(incident, evidence):
        raise RuntimeError("429 quota exceeded")

    monkeypatch.setattr(service, "run_llm", quota_exceeded)

    engine, outcome = service.choose_engine(FakeIncident(), EVIDENCE)

    assert engine == "rules (llm unavailable)"
    assert outcome["findings"]["category"] == "ISSUER_BANK_OUTAGE"


def test_llm_without_answer_falls_back_to_rules(monkeypatch):
    configure_llm(monkeypatch)
    monkeypatch.setattr(service, "run_llm", lambda incident, evidence: {
        "status": "FAILED", "findings": None,
        "verification_problems": ["out of steps"], "trace": [],
    })

    engine, outcome = service.choose_engine(FakeIncident(), EVIDENCE)

    assert engine == "rules (llm gave no answer)"
    assert outcome["status"] == "VERIFIED"