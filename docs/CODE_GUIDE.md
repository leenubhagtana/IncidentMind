# IncidentMind — Complete Code Guide

A walkthrough of every part of the codebase: what each file does, how data moves between components, every threshold and Redis key, and the known quirks.

**Contents**
1. [The big picture](#1-the-big-picture)
2. [Infrastructure: Docker, Kafka, Postgres, Redis](#2-infrastructure)
3. [The shared package](#3-the-shared-package)
4. [Order service (port 8000)](#4-order-service-port-8000)
5. [Payment service (port 8001)](#5-payment-service-port-8001)
6. [Inventory service (port 8002)](#6-inventory-service-port-8002)
7. [Event processor (port 8003)](#7-event-processor-port-8003)
   - 7.1 Startup · 7.2 Config · 7.3 Database tables · 7.4 Redis keys
   - 7.5 Kafka consumer · 7.6 Monitor loop · 7.7 Volume detector
   - 7.8 Failure-rate detector · 7.9 Incident service
8. [Investigation engine](#8-investigation-engine)
9. [API reference](#9-api-reference)
10. [Tests, evals and CI](#10-tests-evals-and-ci)
11. [Scripts](#11-scripts)
12. [One event, start to finish](#12-one-event-start-to-finish)
13. [Known quirks and limitations](#13-known-quirks-and-limitations)

---

## 1. The big picture

IncidentMind is a set of small FastAPI services that talk through **Kafka**. One of them, the **event processor**, watches every event, detects when payments start failing, opens an **incident**, and can **investigate** it. Investigation finds where the failures concentrate, and a **verifier** re-checks every number before anyone sees the result.

```
                 ┌──────────────── Kafka ────────────────┐
POST /orders ──► order-service ──► [order-events] ──┬──► payment-consumer ──┐
                                                    ├──► inventory-consumer │ (prints only)
                                                    │                       │
POST /webhooks/mypay ──► payment-service ──► [payment-events] ◄─────────────┘
                                                    │
                                                    ▼
                                        event-processor (one process, 3 threads)
                     ┌──────────────────────┬──────────────────────┬─────────────────┐
                     │ Thread 1: consumer   │ Thread 2: monitor    │ Main: HTTP API  │
                     │ save → Postgres      │ every 10 s:          │ /incidents      │
                     │ count → Redis        │  volume detector     │ /ai/... analyze │
                     │ bad msg → dead-letter│  failure detector    │ /ai/... approve │
                     └──────────────────────┴──────────────────────┴─────────────────┘
```

| Component | Port | Folder | What it really does |
|---|---|---|---|
| order-service | 8000 | `services/order_service` | Accepts orders and publishes `order_created` |
| payment-service | 8001 | `services/payment_service` | Verifies MyPay webhooks and publishes `payment_completed`/`payment_failed` |
| payment-consumer | – | same folder | Turns every order into a fake `payment_completed` |
| inventory-service | 8002 | `services/inventory_service` | A stub `/inventory/reserve` endpoint |
| inventory-consumer | – | same folder | Prints order events, nothing else |
| event-processor | 8003 | `event_processor` | Storage, detection, incidents, investigation |
| Kafka | 9092 | – | Message bus (single node, KRaft mode, no ZooKeeper) |
| Postgres | 5433 (host) | – | Permanent storage of events, incidents, investigations |
| Redis | 6379 | – | Short-lived counters, windows and baselines |

---

## 2. Infrastructure

### [Dockerfile](../Dockerfile)
**One image is used for every Python service.** It's based on `python:3.13-slim`, installs [requirements.txt](../requirements.txt), and copies `shared/`, `services/` and `event_processor/` into `/srv`. `PYTHONUNBUFFERED=1` makes `print()` output show up immediately in `docker compose logs`.

[.dockerignore](../.dockerignore) keeps `.git`, `.env`, `.venv`, `__pycache__`, all `tests/` folders and `evals/results` out of the image. Your secret `.env` file never goes into the image. Docker Compose passes its values in as environment variables instead.

### [docker-compose.yml](../docker-compose.yml)
- **`x-app` anchor**: shared settings for every Python service. They all build the same image, set `PYTHONPATH=/srv` so `import shared...` works, set `KAFKA_BOOTSTRAP_SERVERS=kafka:29092`, and wait for Kafka to pass its health check before starting.
- **How six services share one image.** Each service has its own folder containing a package named `app`. `working_dir` decides which folder Python starts in, and therefore which `app` gets imported. The `command` decides whether it runs as an API (`uvicorn app.main:app`) or as a consumer (`python -m app.kafka.run_consumer`).
- **Kafka** (`apache/kafka:4.0.1`) has three listeners:
  - `PLAINTEXT :9092` is advertised as `localhost:9092`. Your PC uses this one (scripts, local runs).
  - `INTERNAL :29092` is advertised as `kafka:29092`. Containers use this one to reach each other.
  - `CONTROLLER :9093` is internal to KRaft.
  - `AUTO_CREATE_TOPICS_ENABLE=true`: topics are created the first time something writes to them.
  - **Health check**: `kafka-topics.sh --list` runs every 5 s, with up to 20 retries. If it fails, Compose won't start anything that depends on Kafka. That's what you hit last time.
- **Postgres 16**: database, user and password are all `incidentmind`. It's exposed on host port **5433**, so it won't clash with a Postgres already installed on your machine. Data lives in the named volume `postgres_data`, so it survives `docker compose down` (but not `down -v`).
- **Redis 7**: no volume, so **all Redis data is lost on restart**. That includes the learned baselines and the healthy-window count.
- **payment-service** is the only service that receives `MYPAY_WEBHOOK_SECRET`. It comes from `.env`, with the fallback `local-demo-secret`.
- **event-processor** sets `PYTHONPATH=/srv/event_processor:/srv`, a Postgres URL using host `postgres`, and a Redis URL using host `redis`. It also waits for Postgres to be healthy and for Redis to start.

### [.env.example](../.env.example) / `.env`
These hold only `MYPAY_WEBHOOK_SECRET`. `.env` is git-ignored.

### [requirements.txt](../requirements.txt) / [requirements-dev.txt](../requirements-dev.txt)
- Runtime: FastAPI, uvicorn, SQLAlchemy 2, psycopg2 (the Postgres driver), redis, confluent-kafka, pydantic 2.
- Dev additionally: pytest, fakeredis (an in-memory fake Redis for tests), and httpx (needed by FastAPI's `TestClient`).

---

## 3. The shared package

### [shared/events.py](../shared/events.py) — `ServiceEvent`
This is the one message format every service puts on Kafka:

| Field | Default | Meaning |
|---|---|---|
| `event_id` | random UUID | Unique ID. The event processor uses it to drop duplicates. |
| `event_type` | required | `order_created`, `payment_completed`, `payment_failed`, `service_deployed` |
| `service` | required | Which service produced it |
| `timestamp` | now (UTC) | When it happened |
| `data` | required | Free-form dict with event-specific fields |

### [shared/kafka_publisher.py](../shared/kafka_publisher.py) — `EventPublisher`
Both the order and payment services use this to publish.
- It creates **one Kafka producer per process** with these settings:
  - `linger.ms=5`: wait up to 5 ms so several messages can be batched together.
  - `enable.idempotence=True`: Kafka won't write duplicates if the producer retries.
  - `message.timeout.ms=5000`.
- A **background daemon thread** calls `producer.poll(0.1)` forever. That's what makes delivery callbacks run.
- `publish(event)`:
  1. Creates a `threading.Event` to signal that delivery finished.
  2. Calls `produce()`. If the local queue is full (`BufferError`) or Kafka rejects the message, it raises `PublishError`.
  3. Waits **at most 6 s** for its own message's delivery callback. If none arrives, it raises `PublishError("Timed out…")`.
  4. If the callback reports an error, it logs `❌` and raises `PublishError`.
- Each service's `main.py` turns `PublishError` into an **HTTP 503**. For webhooks, a 5xx tells MyPay to retry later.

---

## 4. Order service (port 8000)

| File | Role |
|---|---|
| [main.py](../services/order_service/app/main.py) | Creates the FastAPI app, `/health`, the `PublishError` → 503 handler, and registers the orders router |
| [routes/orders.py](../services/order_service/app/routes/orders.py) | `POST /orders` |
| [schemas/order.py](../services/order_service/app/schemas/order.py) | `OrderCreate`: `customer_id`, `product_id`, `quantity` (> 0), `amount` (> 0). `OrderResponse` adds `order_id` and `status`. |
| [services/order_service.py](../services/order_service/app/services/order_service.py) | Business logic |
| [kafka/producer.py](../services/order_service/app/kafka/producer.py) | `EventPublisher(topic="order-events")` |

**`POST /orders` step by step**
1. Pydantic validates the body. `quantity: 0` or a missing field gives a **422** with details.
2. `create_order` builds `{order_id: "ord_" + 8 hex chars, …, status: "created"}`.
3. It publishes `ServiceEvent(event_type="order_created", service="order-service", data=<that dict>)` to `order-events` and waits for Kafka to confirm.
4. It returns the dict with **200**, or **503** if Kafka didn't confirm.

Nothing is saved to a database. The order exists only as a Kafka event.

---

## 5. Payment service (port 8001)

### Files
| File | Role |
|---|---|
| [main.py](../services/payment_service/app/main.py) | App, `/health`, the 503 handler, registers the payments and webhooks routers |
| [routes/payments.py](../services/payment_service/app/routes/payments.py) | **Stub** endpoints (see below) |
| [services/payment_service.py](../services/payment_service/app/services/payment_service.py) | `process_payment`: returns a fake `pay_xxxxxxxx` with status `completed` |
| [routes/webhooks.py](../services/payment_service/app/routes/webhooks.py) | **The real entry point for payments** |
| [kafka/producer.py](../services/payment_service/app/kafka/producer.py) | `EventPublisher(topic="payment-events")` |
| [kafka/consumer.py](../services/payment_service/app/kafka/consumer.py) | Order → fake payment converter |
| [kafka/run_consumer.py](../services/payment_service/app/kafka/run_consumer.py) | Entry point for the consumer container |

### Stub endpoints
- `POST /payments` returns a fake payment. **It does not publish to Kafka and saves nothing.**
- `GET /payments/{id}` always returns the same hard-coded payment (`order_001`, 499.99). Only the ID you passed in changes.

### `POST /webhooks/mypay`, step by step
| Step | Check | On failure |
|---|---|---|
| 1 | Is `MYPAY_WEBHOOK_SECRET` set? | **503** "Webhook secret is not configured" |
| 2 | Read the **raw bytes** of the body. The signature covers the exact bytes, so the body must not be parsed and re-serialized first. | – |
| 3 | `HMAC-SHA256(secret, raw_body)` as hex, compared to the `X-MyPay-Signature` header using `hmac.compare_digest`, which takes the same time whether or not the strings match, so timing can't be used to guess the secret | **401** "Invalid signature" |
| 4 | Is the `x-mypay-event-id` header present? | **400** |
| 5 | Parse the JSON and read `payload.payment.entity` | **400** "Unrecognised webhook payload" |
| 6 | Map the event: `payment.captured` → `payment_completed`, `payment.failed` → `payment_failed`, anything else is ignored | **202** `{"status":"ignored"}`, nothing published |
| 7 | Publish to `payment-events` | **503** if Kafka doesn't confirm |
| 8 | – | **202** `{"status":"accepted"}` |

How the webhook becomes an event (`to_service_event`):
- `event_id` = the **`x-mypay-event-id` header**, so a redelivered webhook gets the same ID and is deduplicated later.
- `timestamp` = `payment.created_at`, otherwise `webhook.created_at`, otherwise now. All are Unix seconds, converted to UTC.
- `data` contains `payment_id`, `order_id`, `merchant_id` (from `account_id`), `amount` (**paise ÷ 100 = rupees**), `currency`, `method`, `bank`, `error_code`, `error_source`, `error_step`, `error_reason`. These fields are what the investigation later groups by.

### Payment consumer (`payment-consumer` container)
- Subscribes to `order-events` with consumer group `payment-service` and `auto.offset.reset=latest`, so on first start it reads only new messages. Offsets are committed automatically.
- For **every** message, whatever its type, it publishes `payment_completed` with `{order_id, amount, status: "completed"}`.
- The event has **no bank, method or merchant fields**. In investigations these events show up under the value `"unknown"`.
- It has **no duplicate check**. If the same order message is delivered twice, two payments are created, each with a new `event_id`.

---

## 6. Inventory service (port 8002)

- `POST /inventory/reserve` with `{product_id, quantity > 0}` returns `{reservation_id: "res_…", status: "reserved"}`. It's a **stub**: no stock is tracked and no event is published.
- **Inventory consumer**: subscribes to `order-events` (group `inventory-service`, `latest`), prints each event, and for `order_created` prints "Reserving inventory for …". Nothing else happens.

---

## 7. Event processor (port 8003)

This is where the real logic lives.

### 7.1 Startup — [main.py](../event_processor/app/main.py)
On startup it:
1. Runs `Base.metadata.create_all()`, which creates any missing tables. **There are no migrations.** Changing an existing table (such as adding `resolved_at`) needs a migration or a manual `ALTER TABLE`.
2. Starts a **daemon thread** running `consume_events()` (the Kafka consumer).
3. Starts a **daemon thread** running `start_monitor()` (the detectors).
4. Serves the HTTP API on the main thread.

Daemon threads die with the process. If either thread crashes with an unexpected exception, it simply stops, the API keeps responding, and only the logs show it.

### 7.2 Config — [config.py](../event_processor/app/config.py)
| Variable | Default | Used by |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://incidentmind:incidentmind@localhost:5433/incidentmind` | database.py |
| `REDIS_URL` | `redis://localhost:6379/0` | redis_client.py |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | consumer |
| `DEAD_LETTER_TOPIC` | `events-dead-letter` | consumer |
| `MAX_PROCESSING_ATTEMPTS` | 3 | consumer retries |
| `FAILURE_RATE_THRESHOLD` | 0.10 (10%) | failure detector |
| `MIN_PAYMENT_ATTEMPTS` | 10 | failure detector |
| `RESOLVE_AFTER_HEALTHY_WINDOWS` | 3 | failure detector |
| `INCIDENT_LOOKBACK_SECONDS` | 300 (5 min) | investigation |
| `BASELINE_LOOKBACK_SECONDS` | 3600 (1 h) | investigation |

The defaults point at `localhost`, so the processor also works when run outside Docker (with `start.ps1` or in tests).

### 7.3 Database tables — [models.py](../event_processor/app/models.py)
[database.py](../event_processor/app/database.py) creates the SQLAlchemy engine and `SessionLocal`. [schemas.py](../event_processor/app/schemas.py) holds the `IncidentResponse` API model.

**`events`**: every event ever received.
| Column | Notes |
|---|---|
| `event_id` (PK) | The primary key is what makes duplicate events impossible |
| `event_type`, `service` | |
| `timestamp` | Stored as **naive UTC** (no timezone attached) |
| `data` | JSON |

**`incidents`**
| Column | Notes |
|---|---|
| `incident_id` (PK) | `INC-` + 8 uppercase hex characters |
| `status` | `OPEN` / `RESOLVED` |
| `severity` | `MEDIUM` / `HIGH` / `CRITICAL` |
| `reason` | Text, for example `PAYMENT_FAILURE_SPIKE: 18% of 39…` |
| `affected_service` | `payment-service` or `event-processor` |
| `trigger_event` | `payment_failure_spike` or `event_rate_anomaly` (which detector opened it) |
| `evidence` | JSON snapshot taken when the incident opened |
| `current_rate`, `baseline_rate` | Floats. For failure incidents these are **percentages**; for volume incidents they're **events per window**. |
| `detected_at` | `datetime.utcnow` when created. **There is no `resolved_at`.** |

**`investigations`**: one row per `/analyze` call: `investigation_id` (`INV-…`), `incident_id` (FK), `engine` (`rules`), `status` (`VERIFIED`/`UNVERIFIED`), `result` (JSON with findings and problems), `trace` (always `[]` for now, kept as a placeholder for a future AI engine), `created_at`.

**`action_decisions`**: one row per human decision: `decision_id` (`DEC-…`), `investigation_id` (FK), `action_index`, `decision` (`APPROVED`/`REJECTED`), `decided_by`, `decided_at`.

### 7.4 Every Redis key
| Key | Type | Written by | Read by | Purpose |
|---|---|---|---|---|
| `events:total` | int | consumer | nobody | Lifetime event count |
| `events:type:<type>` | int | consumer | nobody | Lifetime count per type |
| `events:window:<type>` | int | consumer | monitor | Count per type **in the current window**, reset every 10 s |
| `events:last` | JSON string | consumer | nobody | The most recent event |
| `events:recent` | list (max 100) | [event_store.py](../event_processor/app/event_store.py) | incident creation (20 latest) | Recent events snapshot |
| `events:timestamps` | sorted set | consumer (score = arrival time) | monitor | Overall events in the last 10 s |
| `events:rate:history` | list (max 60) | volume detector | volume detector | Baseline of normal event rates |
| `payments:failure_rate:history` | list (max 60) | failure detector | failure detector | Baseline of healthy failure rates |
| `payments:failure_rate:healthy_streak` | int | failure detector | failure detector | Healthy windows in a row |

### 7.5 Kafka consumer — [consumer.py](../event_processor/app/consumer.py)
Settings: group `event-processor`, subscribed to **`order-events` and `payment-events`**, `auto.offset.reset=earliest` (a new group reads the full history), and **`enable.auto.commit=False`**.

The loop for each message:
```
poll(1s) → nothing? continue
         → Kafka error? log, continue
         → process_with_retries(raw)
         → consumer.commit(message)      ← only after saving or dead-lettering
```

`process_with_retries(raw)` returns `"saved"`, `"duplicate"` or `"dead_lettered"`:
1. **`parse_message`** raises `PermanentEventError` if the message is invalid UTF-8 or JSON, isn't a JSON object, or is missing any of `event_id`, `event_type`, `service`, `timestamp` or `data`. In that case the message is dead-lettered immediately, with no retries.
2. Up to **3 attempts** of `save_event`:
   - `PermanentEventError` (an unparseable timestamp) goes straight to the dead-letter topic.
   - Any other exception (Postgres down, network) is retried.
   - If all 3 attempts fail, the message is dead-lettered with the reason "retries exhausted: …".

**`save_event`**:
1. `db.get(Event, event_id)`. If the event already exists, return `False` (duplicate).
2. `to_utc_naive(timestamp)` accepts a `datetime` or an ISO string (a trailing `Z` is allowed), converts it to UTC and drops the timezone.
3. Insert the row and commit.
4. **Only after the commit succeeds**, run `update_counters`, which increments the Redis keys from 7.4. Duplicates therefore never inflate the detector numbers.

**Dead-letter topic**: the raw bytes are sent to `events-dead-letter` with a `reason` header. Nothing reads that topic yet. It's there so you can inspect bad messages later.

### 7.6 Monitor loop — [monitor.py](../event_processor/app/monitor.py)
Every **10 seconds**:
1. **`get_current_event_rate()`** removes members older than 10 s from `events:timestamps`, then counts what's left. That's the overall event rate.
2. **`get_event_evidence()`** reads every `events:window:*` key, for example `{"payment_failed": 7, "payment_completed": 32}`.
3. Runs **`check_event_rate(rate, evidence)`**, the volume detector.
4. Runs **`check_failure_rate(evidence)`**, the failure detector.
5. **`reset_window_counters()`** deletes all `events:window:*` keys.
6. Sleeps 10 s.

A "window" is therefore whatever arrived **between two resets**: roughly 10 s plus however long the checks took. Times are when the event **arrived at the processor**, not the event's own `timestamp`.

### 7.7 Volume detector — [anomaly_detector.py](../event_processor/app/anomaly_detector.py)
Question it answers: "Are there far more events than usual?"

```
rate == 0               → "No events", resolve open volume incident, stop
history < 10 samples    → "Learning normal behaviour… n/10", save rate, stop
mean <= 0               → skip, save rate
z = (rate − mean) / stdev            (0 if stdev is 0)
anomaly if rate ≥ 5 AND (z ≥ 3.0, or rate ≥ 3×mean when stdev is 0)
not anomaly → save rate to history, resolve open volume incident
anomaly     → classify, create incident (trigger_event = event_rate_anomaly)
```
- **Learning phase**: the first 10 windows that have traffic only build the baseline.
- **A spike never enters the baseline**, so a long spike can't make itself look normal.
- **Classification** (`classify_incident`) looks only at `order_created` and `payment_completed`:
  - orders ≥ 2 × payments → `ORDER_SPIKE`
  - payments ≥ 2 × orders → `PAYMENT_SPIKE`
  - both present → `MULTI_SERVICE_ANOMALY`
  - otherwise → `GENERAL_TRAFFIC_ANOMALY`
- **Severity** (`calculate_severity` in incident_service): current ÷ baseline ≥ 5 → CRITICAL, ≥ 3 → HIGH, otherwise MEDIUM.
- **Resolves** on the first normal window **or the first empty one**, so usually within 10–20 s.

### 7.8 Failure-rate detector — [failure_detector.py](../event_processor/app/failure_detector.py)
Question it answers: "Are too many payments failing?" Total volume can look normal during a bank outage, which is why this is a separate signal.

```
attempts = payment_failed + payment_completed
rate     = failed / attempts

attempts < 10           → too little data: do nothing (healthy count kept)
rate < 10%   (healthy)  → push rate to healthy history (max 60)
                          healthy_streak += 1
                          if healthy_streak ≥ 3 → resolve open failure incident
rate ≥ 10%   (failing)  → healthy_streak = 0
                          create incident (trigger_event = payment_failure_spike)
```
- Severity: rate ≥ 50% → CRITICAL, ≥ 30% → HIGH, otherwise MEDIUM.
- `current_rate` = rate × 100. `baseline_rate` = the average of the healthy history × 100.
- **Why the threshold is only 10%**: if one bank of five (about 20% of traffic) fails 80% of the time, the overall failure rate rises by only about 16 points.

### 7.9 Incident service — [incident_service.py](../event_processor/app/incident_service.py)
- **`get_open_incident(db, trigger_event)`** returns the newest OPEN incident **for that trigger only**. There's one open incident per signal, so a traffic spike can't hide a payment outage that starts during it.
- **`create_incident(...)`**:
  - If an OPEN incident already exists for that trigger, it prints "Existing OPEN incident found" and **returns it unchanged**. Its evidence stays frozen at the first window.
  - Otherwise it generates `INC-XXXXXXXX` and severity (passed in, or computed). It builds `evidence` = `{current_event_rate, baseline_event_rate, rate_multiplier, detection_reason, event_counts, recent_events (20)}`, then inserts, commits and logs `🚨 INCIDENT CREATED`.
  - On error it rolls back, logs the error, and returns `None`.
- **`resolve_open_incident(trigger_event)`** sets `status = "RESOLVED"`, commits and logs `✅ INCIDENT RESOLVED`. It records no timestamp.

---

## 8. Investigation engine

Triggered by `POST /ai/incidents/{id}/analyze`, in [routes/ai.py](../event_processor/app/routes/ai.py).

### 8.0 Which analyst runs
- `trigger_event == payment_failure_spike` → the **investigation engine** (below). **Each call creates a new investigation row.**
- Anything else (volume incidents) → **[ai_analyst.py](../event_processor/app/ai_analyst.py)**. Despite the name, this isn't AI. It uses fixed if/else rules on order and payment counts and returns `summary`, `root_cause`, `impact`, `confidence` and a list of recommendations. It deliberately says it "does not establish the underlying cause". Nothing is saved.

### 8.1 Loading evidence — [investigation/service.py](../event_processor/app/investigation/service.py)
Using `detected_at` (D) of the incident:
```
baseline window: [D − 65 min, D − 5 min)     ← "what normal looked like"
incident window: [D − 5 min,  D]             ← "what went wrong"
```
- It loads **all events with a timestamp in [D − 65 min, D]**.
- Payment events (`payment_completed`, `payment_failed`) are split into **incident_events** and **baseline_events** by time.
- `service_deployed` events become **deployments**.
- Events **after** D are not considered.

### 8.2 Analysis helpers — [investigation/evidence.py](../event_processor/app/investigation/evidence.py)
Grouping dimensions: `bank`, `method`, `merchant_id`, `error_code`, `error_source`. A missing value is grouped as `"unknown"`.

- **`summarize(events)`** returns `{attempts, failed, failure_rate}`.
- **`group_rows(evidence, dimension)`** returns one row per value (for example per bank), sorted by `failed`, highest first:
  `{value, attempts, failed, failure_rate, baseline_failure_rate, share_of_failures}`
  where `share_of_failures` = this value's failures ÷ all incident failures.
- **`concentration(evidence, dimension)`** answers "does one value explain the failures?" It takes the top row and returns **`None` (no concentration)** if any of these is true:
  - it has 0 failures
  - its value is `"unknown"`
  - its `share_of_failures` is under **60%**
  - other values exist and its failure rate is below **max(2 × the others' rate, 15%)**

  The last rule exists because HDFC could hold 60% of failures simply by handling 60% of traffic. It must also fail much more often than everyone else.
- **`failure_onset(evidence)`** finds when failures started, using a **CUSUM change-point** method:
  1. Sort the events by time and mark each failure as 1, success as 0. With fewer than 3 failures, it returns `None`.
  2. Keep a running total of (flag − average failure rate). Before the change the total drifts downward; afterwards it climbs. The **lowest point** of the total is the change point.
  3. Return the timestamp of the first failure at or after that point.

  This is better than "the first failure ever", because a single random customer decline before a deploy would otherwise make the deploy look innocent.
- **`metric_value(evidence, dimension, value, metric)`** returns the **trusted** recomputed number for a claim, or `None` if that dimension/value doesn't exist. The verifier relies on it.

### 8.3 Rule engine — [investigation/rules.py](../event_processor/app/investigation/rules.py)
`triage(evidence)` tries these checks **in order** and returns the first match:

| # | Check | Result category | Scope |
|---|---|---|---|
| 1 | Failures concentrate on `error_source` **and** the top value is `customer` | `CUSTOMER_SIDE_DECLINES` | none |
| 2 | Concentrated on a `merchant_id` | `MERCHANT_CONFIGURATION` | that merchant |
| 3 | Concentrated on a `bank` | `ISSUER_BANK_OUTAGE` | that bank |
| 4 | Concentrated on a `method` | `PAYMENT_METHOD_OUTAGE` | that method |
| 5 | A failure onset exists and **some deployment happened at or before it** | `INTERNAL_REGRESSION` | none |
| 6 | Otherwise | `INCONCLUSIVE` (confidence LOW) | none |

Matches 1–5 get confidence **MEDIUM**, plus:
- **claims**: overall `failed`, overall `failure_rate` and (for 1–4) that value's `share_of_failures`
- **proposed action**: "Review failures for bank=HDFC." (risk LOW), or "Review the most recent deployment."
- **root_cause** text that states honestly: "this shows where, not why."

### 8.4 Verifier — [investigation/verifier.py](../event_processor/app/investigation/verifier.py)
`verify(findings, evidence)` returns a list of problems. An empty list means **VERIFIED**.
1. **Every claim is recomputed** with `metric_value`:
   - The data doesn't exist (for example `bank=FAKEBANK`): "Claim references data that does not exist".
   - Counts must match **exactly**. Rates may differ by up to **±0.01**. Otherwise: "Wrong number".
2. If the category is `INCONCLUSIVE`, it stops here.
3. There must be at least one claim, and HIGH confidence needs at least 2 claims.
4. Bank, method and merchant categories must be **scoped to the matching dimension**, and `concentration()` must independently find the **same value**.
5. `INTERNAL_REGRESSION` needs a failure onset **and** a deployment at or before it.
6. `CUSTOMER_SIDE_DECLINES` needs `error_source=customer` to be concentrated.

The verifier checks facts and preconditions. It **doesn't prove the cause**: a finding can pass verification and still be wrong. The eval counts those cases as `verified_but_wrong`.

### 8.5 Schemas — [investigation/schemas.py](../event_processor/app/investigation/schemas.py)
Pydantic models restrict every field to a fixed set of allowed values. `Category`, `ClaimDimension`, `ClaimMetric`, `Scope.dimension`, `ProposedAction.risk` and `Findings.confidence` are all `Literal` types, so an unexpected value can't even be constructed.

### 8.6 Human approval
`POST /ai/investigations/{id}/actions/{index}` with `{"decision": "APPROVED"|"REJECTED", "decided_by": "name"}`:
- Unknown investigation → **404**. Index out of range → **404**.
- **APPROVED on an UNVERIFIED investigation → 409.** Rejecting is always allowed.
- Saves an `action_decisions` row and returns it. **Nothing is executed.** The same action can be decided more than once.

---

## 9. API reference

| Method & URL | Body | Responses |
|---|---|---|
| `GET :8000/health` (same on every service) | – | 200 |
| `POST :8000/orders` | `customer_id, product_id, quantity>0, amount>0` | 200, 422, 503 |
| `POST :8001/payments` | `order_id, amount>0, currency="INR"` | 200 (stub) |
| `GET :8001/payments/{id}` | – | 200 (hard-coded) |
| `POST :8001/webhooks/mypay` | MyPay JSON + `X-MyPay-Signature` + `x-mypay-event-id` headers | 202, 400, 401, 503 |
| `POST :8002/inventory/reserve` | `product_id, quantity>0` | 200 (stub) |
| `GET :8003/incidents?status=OPEN` | – | 200 list, newest first (status is case-insensitive) |
| `GET :8003/incidents/{id}` | – | 200, 404 |
| `POST :8003/incidents/deployments` | `{service, version}` | 201 `{event_id}` |
| `POST :8003/ai/incidents/{id}/analyze` | – | 200, 404 |
| `POST :8003/ai/investigations/{id}/actions/{n}` | `{decision, decided_by}` | 200, 404, 409 |

`POST /incidents/deployments` writes a `service_deployed` event **directly to Postgres**, timestamped now, with ID `deploy-<hex>`. It bypasses Kafka and Redis, so deployments never count toward the detectors. CI is meant to call it after each deploy.

Every service also has interactive docs at `http://localhost:<port>/docs`.

---

## 10. Tests, evals and CI

### Configuration
[pytest.ini](../pytest.ini) sets `pythonpath = event_processor .` and runs tests in `event_processor/tests` and `services/payment_service/tests`.

### [event_processor/tests/conftest.py](../event_processor/tests/conftest.py)
- Points `DATABASE_URL` at a **temporary SQLite file**, so no Postgres is needed.
- Replaces the Redis client with **fakeredis**. This must happen before any module imports it.
- Before every test it drops and recreates all tables and flushes Redis, so each test starts clean.

### Test files
| File | What it proves |
|---|---|
| [test_consumer.py](../event_processor/tests/test_consumer.py) | Duplicates are stored and counted once. Bad JSON, missing fields and bad timestamps go to dead-letter without retries. Temporary errors succeed on retry. Exhausted retries go to dead-letter. |
| [test_detectors.py](../event_processor/tests/test_detectors.py) | High failure rate opens an incident with the right severity. A single-bank outage (13.5%) is caught. Low volume is ignored. Repeat spikes create one incident. 3 healthy windows resolve it, one doesn't, a failing window resets the count, quiet windows don't count. The two signals are independent. Zero traffic resolves volume incidents. Spikes stay out of the baseline. |
| [test_investigation.py](../event_processor/tests/test_investigation.py) | Breakdown numbers add up. Concentration finds the failing bank and ignores an even spread. Onset isn't fooled by stray declines. The verifier accepts honest findings and rejects wrong numbers, invented values, deploys after onset, and banks without concentration. |
| [test_api.py](../event_processor/tests/test_api.py) | `/analyze` runs the rules and gets VERIFIED ISSUER_BANK_OUTAGE on HDFC. Decisions are recorded. An unknown action gives 404. Deployments are recorded. |
| [payment_service/tests/test_webhooks.py](../services/payment_service/tests/test_webhooks.py) | A valid failed webhook becomes the right event (ID, type, bank, rupees, merchant). Bad signature → 401 and nothing published. Tampered body → 401. Unknown event → ignored. Missing event ID → 400. Kafka is replaced with a fake module. |

### Evals — [evals/scenarios.py](../evals/scenarios.py) and [evals/run.py](../evals/run.py)
These generate **synthetic** incidents where the true cause is known, then score the rule engine on them.
- Each scenario has a baseline of 400 healthy events (3% customer declines, spread over the hour before) and an incident window of 300 events over 5 minutes.
- **9 scenario types × 5 random seeds = 45 cases.**

| Scenario | Expected answer | Hard? |
|---|---|---|
| bank_outage (HDFC fails 70%) | ISSUER_BANK_OUTAGE / HDFC | |
| upi_outage (UPI fails 65%) | PAYMENT_METHOD_OUTAGE / upi | |
| deploy_regression (40% internal errors after deploy) | INTERNAL_REGRESSION | |
| merchant_config (acc_3 fails 90%) | MERCHANT_CONFIGURATION / acc_3 | |
| customer_declines (28% everywhere) | CUSTOMER_SIDE_DECLINES | |
| outage_with_later_deploy (deploy lands **after** the SBIN outage) | ISSUER_BANK_OUTAGE / SBIN | ✔ |
| card_release_regression (bad release breaks cards only) | INTERNAL_REGRESSION | ✔ |
| bank_outage_on_big_merchant (acc_1 sits on failing ICIC) | ISSUER_BANK_OUTAGE / ICIC | ✔ |
| mixed_low_signal (nothing stands out) | INCONCLUSIVE | ✔ |

- `run.py` also **plants false findings** for each case: an inflated number, an invented bank (`FAKEBANK`), and a regression with no deployment. It then checks that the verifier rejects them all.
- Results so far (README): standard **25/25**, hard **10/20**, verified-but-wrong **10**, planted errors caught **120/120**. The rule engine fails some hard cases because it checks merchant before bank, and concentration before deploy timing.
- The report is written to `evals/results/rules.json`, which is git-ignored.

### CI — [.github/workflows/ci.yml](../.github/workflows/ci.yml)
On every push or PR: Ubuntu, Python 3.13, install dev requirements, `pytest`, then `python -m evals.run`.

---

## 11. Scripts

### [scripts/simulate_outage.py](../scripts/simulate_outage.py)
- Sends **5 signed webhooks per second** to `WEBHOOK_URL` (default `http://localhost:8001/webhooks/mypay`), signed with `MYPAY_WEBHOOK_SECRET` (default `local-demo-secret`).
- **60 s healthy**: every bank fails 2% of the time.
- **40 s outage**: HDFC fails **80%**, other banks 2%. HDFC is about 1 in 5 payments, so the overall rate is about 17%, enough to trip the 10% threshold.
- Payments are netbanking, ₹100–₹5,000, with merchants `acc_1`–`acc_8` and a random event ID per webhook.

### [start.ps1](../start.ps1) / [stop.ps1](../stop.ps1)
- `start.ps1` runs `docker compose up -d`, waits until Kafka answers, creates the `order-events` and `payment-events` topics (1 partition each), then **opens 6 PowerShell windows** running each service from `.venv` with `--reload` on ports 8000–8003.
- `stop.ps1` runs `docker compose down` and asks you to close those windows yourself.
- ⚠ See quirk #1 below: these local windows clash with the Docker containers.

---

## 12. One event, start to finish

Following a single **failed HDFC payment**:

1. **MyPay (or Postman)** sends `POST :8001/webhooks/mypay` with the JSON body, an HMAC signature and an event ID.
2. **payment-service** checks the secret, verifies the signature against the raw body, checks the event ID, parses the JSON, and converts it to `ServiceEvent(event_id=<header>, event_type="payment_failed", data={bank:"HDFC", amount: paise/100, …})`.
3. **EventPublisher** publishes to Kafka topic **`payment-events`** and waits up to 6 s for confirmation. The webhook returns **202**.
4. **event-processor, consumer thread**, picks the message up: parse → not a duplicate → INSERT into `events` → commit → Redis: `events:window:payment_failed += 1`, added to `events:timestamps` and `events:recent` → Kafka offset committed.
5. **Monitor thread**, within 10 s, reads `{"payment_failed": 7, "payment_completed": 32}`:
   - Volume detector: 39 events against a baseline of ~65 isn't a spike, so the result is NORMAL.
   - Failure detector: 39 ≥ 10 attempts and 18% ≥ 10%, so the healthy count is reset and **INC-XXXX is created** (MEDIUM, `payment_failure_spike`).
   - The window counters are reset.
6. Later windows: while failures continue, the existing incident is reused. After **3 healthy windows in a row** it is marked **RESOLVED**.
7. **You** call `POST :8003/ai/incidents/INC-XXXX/analyze`. It loads 65 minutes of payments, groups them, finds ≥ 60% of failures on HDFC with a much higher failure rate than the other banks → `ISSUER_BANK_OUTAGE / bank=HDFC`. The verifier recomputes the numbers → **VERIFIED**, saved as `INV-XXXX`.
8. **You** approve action 0. An `action_decisions` row is saved, and nothing is executed.

---

## 13. Known quirks and limitations

Things I noticed while reading the code, roughly most important first. None of these are fixed yet.

1. **`start.ps1` starts every service twice.** `docker compose up -d` already starts all the app containers on ports 8000–8003. The local PowerShell windows then try to use the same ports, which normally fails with "address already in use". If a local copy does start, it's unclear which copy is answering your requests. Use either Docker **or** the local windows (start only kafka, postgres and redis in Docker), not both.
2. **Every order counts as a successful payment.** The payment consumer publishes a `payment_completed` for each order. Sending orders during an outage **lowers the failure rate** and can resolve incidents early. In investigations these events appear under `bank="unknown"`.
3. **The payment consumer ignores the event type** and has no duplicate check. A duplicated order message creates two payments.
4. **Events can be missed by the monitor.** Events counted between `get_event_evidence()` and `reset_window_counters()` are deleted without being checked. Windows are based on arrival time, so a backlog from a slow consumer lands in one window all at once.
5. **The two detectors use slightly different windows.** The volume rate comes from a 10-second sorted set, while the failure counts are "since the last reset".
6. **An incident's evidence is frozen.** A repeat spike returns the existing incident without updating its counts or severity, even if the outage gets worse.
7. **No `resolved_at` and no migrations.** You can't tell how long an incident lasted, and schema changes need manual `ALTER TABLE`.
8. **Redis has no persistence.** A Redis restart wipes the baselines, so the volume detector relearns for 10 windows and the healthy count starts at 0.
9. **The investigation only sees events up to `detected_at`.** It reads the first 5 minutes before detection, not what happened afterwards. It also relies on the payment `created_at` sent by the client: a wrong clock on the sender puts events outside the window.
10. **Each `/analyze` call creates a new investigation**, and the same action can be approved several times.
11. **Stub endpoints**: `POST /payments`, `GET /payments/{id}` and `POST /inventory/reserve` return fake data and publish nothing.
12. **Volume classification ignores `payment_failed`**, so a burst of failures alone counts as `GENERAL_TRAFFIC_ANOMALY`.
13. **Deprecation warnings**: `@app.on_event("startup")` (use lifespan), Pydantic `class Config` (use `ConfigDict`), `datetime.utcnow`.
14. **`.gitignore` typo**: `__pycache__/.venv/` is two rules accidentally merged onto one line. `.venv` is only ignored because a virtual environment contains its own `.gitignore`.
15. **Postgres credentials are hard-coded** in `docker-compose.yml`. That's fine locally, not for any shared deployment.
16. **Kafka needs memory.** With about 2.8 GB given to Docker, it misses heartbeats and goes unhealthy under load.
