import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request

from app.kafka.producer import publish_event
from shared.events import ServiceEvent


router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"]
)

EVENT_TYPES = {
    "payment.captured": "payment_completed",
    "payment.failed": "payment_failed",
}


def signature_is_valid(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def to_service_event(webhook: dict, event_id: str) -> ServiceEvent | None:
    event_type = EVENT_TYPES.get(webhook.get("event"))

    if event_type is None:
        return None

    payment = webhook["payload"]["payment"]["entity"]

    timestamp = datetime.fromtimestamp(
        payment.get("created_at")
        or webhook.get("created_at")
        or datetime.now(timezone.utc).timestamp(),
        tz=timezone.utc
    )

    return ServiceEvent(
        # Razorpay's own ID makes redelivered webhooks deduplicate downstream.
        event_id=event_id,
        event_type=event_type,
        service="payment-service",
        timestamp=timestamp,
        data={
            "payment_id": payment.get("id"),
            "order_id": payment.get("order_id"),
            "merchant_id": webhook.get("account_id"),
            # Razorpay amounts are in paise.
            "amount": (payment.get("amount") or 0) / 100,
            "currency": payment.get("currency"),
            "method": payment.get("method"),
            "bank": payment.get("bank"),
            "error_code": payment.get("error_code"),
            "error_source": payment.get("error_source"),
            "error_step": payment.get("error_step"),
            "error_reason": payment.get("error_reason"),
        }
    )


@router.post("/razorpay", status_code=202)
async def receive_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(default=""),
    x_razorpay_event_id: str = Header(default=""),
):
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    if not secret:
        raise HTTPException(503, "Webhook secret is not configured")

    # The signature covers the exact bytes received, so verify before parsing.
    raw_body = await request.body()

    if not signature_is_valid(raw_body, x_razorpay_signature, secret):
        raise HTTPException(401, "Invalid signature")

    if not x_razorpay_event_id:
        raise HTTPException(400, "Missing x-razorpay-event-id header")

    try:
        event = to_service_event(
            json.loads(raw_body),
            x_razorpay_event_id
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(400, "Unrecognised webhook payload") from exc

    if event is None:
        return {"status": "ignored"}

    publish_event(event)

    return {"status": "accepted"}
