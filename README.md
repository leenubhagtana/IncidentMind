# IncidentMind

Event-driven incident detection for payments, with automated investigation whose conclusions are checked by code before anyone sees them.

When payment failures spike, IncidentMind opens an incident and investigates it: which bank, method or merchant is failing, whether a deployment lines up, and what to do next. Every number in the answer is recomputed from the raw events. Actions are proposals that a person approves.

```
MyPay webhooks ─ signature check ─ payment-service ─┐
order-service ─────────────────────────────────────────┤ Kafka
                                                       ▼
                       event-processor: idempotent consumer, dead-letter topic
                                                       │
                     Postgres (events)   Redis (windows and baselines)
                                                       │
                          detectors: volume z-score + payment failure rate
                                                       │
                                                incident opened
                                                       │
           rule engine ─ findings ─ verifier ─ human approval
```

## Why the verifier matters

The verifier checks each investigation against the raw events and rejects findings when:

- a reported number does not match the events
- a claim references data that does not exist
- a bank, method or merchant is blamed without failures concentrating there
- a deployment is blamed but no deployment came before the failures began
- HIGH confidence rests on fewer than two claims

Findings that fail are labelled `UNVERIFIED`, and their actions cannot be approved.

The verifier checks facts and required conditions. It does not prove the cause, so a conclusion can pass and still be wrong. The eval tracks that as `verified_but_wrong`.

## Evaluation

`evals/` holds 9 synthetic incident types across 5 seeds, each with a known cause. Four types are hard on purpose, such as a bad card release that imitates a card network outage.

| Engine | Standard | Hard | Verified but wrong |
| --- | --- | --- | --- |
| Rule engine (baseline) | 25/25 | 10/20 | 10 |

The verifier rejected 120 of 120 planted false findings. All of this data is generated, so these results do not show performance on real traffic.

## Run it

Needs Docker.

```bash
cp .env.example .env
docker compose up --build
python scripts/simulate_outage.py
```

Then open http://localhost:8003/docs, list incidents with `GET /incidents`, and call `POST /ai/incidents/{id}/analyze`.

Run the tests and evals:

```bash
pip install -r requirements-dev.txt
pytest
PYTHONPATH=event_processor:. python -m evals.run
```

## Design decisions

- **Separate failure-rate detector.** A bank outage can leave event volume flat, so the volume detector alone would miss it.
- **10% failure threshold.** A complete outage at a bank with 20% of traffic moves the overall rate by only about 16 points.
- **Idempotent consumer.** Kafka and MyPay can both deliver twice. The MyPay event ID becomes the event ID, and counters update only after a new row commits.
- **Dead-letter topic.** Bad data skips retries, transient errors retry first, and neither blocks the partition.
- **Human approval.** The system proposes actions and never runs them.
- **Healthy windows only in baselines.** An incident cannot raise its own baseline.

## Limits

- The rule engine shows where failures concentrate, not why. It gets half of the hard cases wrong.
- One open incident is kept per signal, so two simultaneous failure causes share an incident.
- Approvals are recorded and do not trigger any action.
