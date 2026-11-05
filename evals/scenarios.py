"""
Synthetic incidents with a known cause. All data here is generated.

The hard cases exist because concentration alone misleads: a bad card release
looks like a card outage, and one large merchant can look like the cause of a
bank outage it merely sits on top of.
"""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.investigation.evidence import Evidence


DETECTED_AT = datetime(2026, 1, 15, 12, 0, 0)
BANKS = ["HDFC", "ICIC", "SBIN", "UTIB", "KKBK"]
METHODS = ["upi", "card", "netbanking"]
MERCHANTS = [f"acc_{index}" for index in range(1, 9)]

CUSTOMER_ERROR = ("BAD_REQUEST_ERROR", "customer")
BANK_ERROR = ("GATEWAY_ERROR", "bank")
GATEWAY_ERROR = ("GATEWAY_ERROR", "gateway")
INTERNAL_ERROR = ("SERVER_ERROR", "internal")


@dataclass
class Scenario:
    name: str
    category: str
    scope: tuple[str, str] | None
    hard: bool
    evidence: Evidence


def event(rng, timestamp, failed, error=None, **overrides) -> dict:
    data = {
        "bank": rng.choice(BANKS),
        "method": rng.choice(METHODS),
        "merchant_id": rng.choice(MERCHANTS),
        "error_code": None,
        "error_source": None,
    }
    data.update(overrides)

    if failed:
        data["error_code"], data["error_source"] = error

    return {
        "event_id": f"evt_{rng.getrandbits(64):x}",
        "event_type": "payment_failed" if failed else "payment_completed",
        "timestamp": timestamp,
        "data": data,
    }


def healthy_baseline(rng) -> list[dict]:
    return [
        event(
            rng,
            DETECTED_AT - timedelta(minutes=70) + timedelta(seconds=index * 8),
            rng.random() < 0.03,
            CUSTOMER_ERROR,
        )
        for index in range(400)
    ]


def window(rng, make_event, count=300, start_minutes=5) -> list[dict]:
    return [
        make_event(
            DETECTED_AT
            - timedelta(minutes=start_minutes)
            + timedelta(seconds=index * (start_minutes * 60 / count))
        )
        for index in range(count)
    ]


def background(rng, timestamp) -> dict:
    return event(rng, timestamp, rng.random() < 0.03, CUSTOMER_ERROR)


def bank_outage(rng):
    def make(timestamp):
        bank = rng.choice(BANKS)

        if bank == "HDFC" and rng.random() < 0.7:
            return event(rng, timestamp, True, BANK_ERROR, bank="HDFC")

        return event(
            rng, timestamp, rng.random() < 0.03, CUSTOMER_ERROR, bank=bank
        )

    return window(rng, make), []


def upi_outage(rng):
    def make(timestamp):
        method = rng.choice(METHODS)

        if method == "upi" and rng.random() < 0.65:
            return event(rng, timestamp, True, GATEWAY_ERROR, method="upi")

        return event(
            rng, timestamp, rng.random() < 0.03, CUSTOMER_ERROR, method=method
        )

    return window(rng, make), []


def deploy_regression(rng):
    deployed_at = DETECTED_AT - timedelta(minutes=4)

    def make(timestamp):
        if timestamp >= deployed_at and rng.random() < 0.4:
            return event(rng, timestamp, True, INTERNAL_ERROR)

        return background(rng, timestamp)

    deployment = {
        "timestamp": deployed_at,
        "service": "payment-service",
        "version": "2.14.0",
    }

    return window(rng, make), [deployment]


def merchant_config(rng):
    def make(timestamp):
        merchant = rng.choice(MERCHANTS)

        if merchant == "acc_3" and rng.random() < 0.9:
            return event(
                rng, timestamp, True,
                ("BAD_REQUEST_ERROR", "business"),
                merchant_id="acc_3",
            )

        return event(
            rng, timestamp, rng.random() < 0.03, CUSTOMER_ERROR,
            merchant_id=merchant,
        )

    return window(rng, make), []


def customer_declines(rng):
    def make(timestamp):
        return event(rng, timestamp, rng.random() < 0.28, CUSTOMER_ERROR)

    return window(rng, make), []


def outage_with_later_deploy(rng):
    """A deployment lands after the bank outage began. It is a red herring."""

    onset = DETECTED_AT - timedelta(minutes=4, seconds=30)

    def make(timestamp):
        bank = rng.choice(BANKS)

        if timestamp >= onset and bank == "SBIN" and rng.random() < 0.75:
            return event(rng, timestamp, True, BANK_ERROR, bank="SBIN")

        return event(
            rng, timestamp, rng.random() < 0.03, CUSTOMER_ERROR, bank=bank
        )

    deployment = {
        "timestamp": DETECTED_AT - timedelta(minutes=1),
        "service": "payment-service",
        "version": "2.14.1",
    }

    return window(rng, make), [deployment]


def card_release_regression(rng):
    """A bad release breaks one method, so it imitates a method outage."""

    deployed_at = DETECTED_AT - timedelta(minutes=4)

    def make(timestamp):
        method = rng.choice(METHODS)

        if (
            timestamp >= deployed_at
            and method == "card"
            and rng.random() < 0.7
        ):
            return event(rng, timestamp, True, INTERNAL_ERROR, method="card")

        return event(
            rng, timestamp, rng.random() < 0.03, CUSTOMER_ERROR, method=method
        )

    deployment = {
        "timestamp": deployed_at,
        "service": "card-tokenizer",
        "version": "1.9.0",
    }

    return window(rng, make), [deployment]


def bank_outage_on_big_merchant(rng):
    """One large merchant sits on a failing bank but is not itself the cause."""

    def make(timestamp):
        if rng.random() < 0.3:
            failed = rng.random() < 0.8
            return event(
                rng, timestamp, failed,
                BANK_ERROR, bank="ICIC", merchant_id="acc_1",
            )

        return background(rng, timestamp)

    return window(rng, make), []


def mixed_low_signal(rng):
    """Nothing separates the candidates, so the honest answer is INCONCLUSIVE."""

    errors = [CUSTOMER_ERROR, BANK_ERROR, GATEWAY_ERROR, INTERNAL_ERROR]

    def make(timestamp):
        return event(rng, timestamp, rng.random() < 0.25, rng.choice(errors))

    return window(rng, make), []


DEFINITIONS = [
    (bank_outage, "ISSUER_BANK_OUTAGE", ("bank", "HDFC"), False),
    (upi_outage, "PAYMENT_METHOD_OUTAGE", ("method", "upi"), False),
    (deploy_regression, "INTERNAL_REGRESSION", None, False),
    (merchant_config, "MERCHANT_CONFIGURATION", ("merchant_id", "acc_3"), False),
    (customer_declines, "CUSTOMER_SIDE_DECLINES", None, False),
    (outage_with_later_deploy, "ISSUER_BANK_OUTAGE", ("bank", "SBIN"), True),
    (card_release_regression, "INTERNAL_REGRESSION", None, True),
    (bank_outage_on_big_merchant, "ISSUER_BANK_OUTAGE", ("bank", "ICIC"), True),
    (mixed_low_signal, "INCONCLUSIVE", None, True),
]


def build_scenarios(seeds=range(5)) -> list[Scenario]:
    scenarios = []

    for seed in seeds:
        for builder, category, scope, hard in DEFINITIONS:
            rng = random.Random(f"{builder.__name__}-{seed}")
            incident_events, deployments = builder(rng)

            scenarios.append(Scenario(
                name=f"{builder.__name__}#{seed}",
                category=category,
                scope=scope,
                hard=hard,
                evidence=Evidence(
                    detected_at=DETECTED_AT,
                    incident_events=incident_events,
                    baseline_events=healthy_baseline(rng),
                    deployments=deployments,
                ),
            ))

    return scenarios
