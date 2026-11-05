"""
Sends signed, MyPay-format test webhooks to the running stack: healthy
traffic, then a simulated HDFC outage. All data is generated.

  python scripts/simulate_outage.py
"""
import hashlib
import hmac
import json
import os
import random
import time
import urllib.request
import uuid


URL = os.getenv("WEBHOOK_URL", "http://localhost:8001/webhooks/mypay")
SECRET = os.getenv("MYPAY_WEBHOOK_SECRET", "local-demo-secret")
BANKS = ["HDFC", "ICIC", "SBIN", "UTIB", "KKBK"]
RATE_PER_SECOND = 5


def send(failed: bool, bank: str) -> None:
    now = int(time.time())
    payment = {
        "id": f"pay_{uuid.uuid4().hex[:14]}",
        "amount": random.randint(10_000, 500_000),
        "currency": "INR",
        "status": "failed" if failed else "captured",
        "order_id": f"order_{uuid.uuid4().hex[:14]}",
        "method": "netbanking",
        "bank": bank,
        "error_code": "GATEWAY_ERROR" if failed else None,
        "error_source": "bank" if failed else None,
        "error_step": "payment_authorization" if failed else None,
        "error_reason": "payment_failed" if failed else None,
        "created_at": now,
    }
    body = json.dumps({
        "entity": "event",
        "account_id": f"acc_{random.randint(1, 8)}",
        "event": "payment.failed" if failed else "payment.captured",
        "contains": ["payment"],
        "created_at": now,
        "payload": {"payment": {"entity": payment}},
    }).encode()

    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

    request = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json",
        "X-MyPay-Signature": signature,
        "x-mypay-event-id": f"evt_{uuid.uuid4().hex}",
    })
    urllib.request.urlopen(request, timeout=5).read()


def run(seconds: int, outage: bool) -> None:
    for _ in range(seconds * RATE_PER_SECOND):
        bank = random.choice(BANKS)
        failed = (
            random.random() < 0.8
            if outage and bank == "HDFC"
            else random.random() < 0.02
        )
        send(failed, bank)
        time.sleep(1 / RATE_PER_SECOND)


if __name__ == "__main__":
    print("Sending healthy traffic for 60 seconds...")
    run(60, outage=False)
    print("Starting simulated HDFC outage for 40 seconds...")
    run(40, outage=True)
    print("Done. Open http://localhost:8003/incidents?status=OPEN")
