from typing import Literal

from pydantic import BaseModel, Field


Category = Literal[
    "ISSUER_BANK_OUTAGE",
    "PAYMENT_METHOD_OUTAGE",
    "INTERNAL_REGRESSION",
    "MERCHANT_CONFIGURATION",
    "CUSTOMER_SIDE_DECLINES",
    "INCONCLUSIVE",
]

ClaimDimension = Literal[
    "overall",
    "bank",
    "method",
    "merchant_id",
    "error_code",
    "error_source",
]

ClaimMetric = Literal[
    "attempts",
    "failed",
    "failure_rate",
    "baseline_failure_rate",
    "share_of_failures",
]


class Claim(BaseModel):
    dimension: ClaimDimension
    value: str = ""
    metric: ClaimMetric
    reported_value: float


class Scope(BaseModel):
    dimension: Literal[
        "bank",
        "method",
        "merchant_id",
        "error_code",
        "error_source",
    ]
    value: str


class ProposedAction(BaseModel):
    action: str
    risk: Literal["LOW", "MEDIUM", "HIGH"]


class Findings(BaseModel):
    category: Category
    scope: Scope | None = None
    summary: str
    root_cause: str
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    claims: list[Claim] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
