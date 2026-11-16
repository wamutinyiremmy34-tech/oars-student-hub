"""FakeProvider: development and automated tests ONLY. It keeps payment state in memory, signs webhooks
with HMAC-SHA256 (timestamped, to defeat replays) and lets tests/dev flip a payment to paid or failed.

It is never available for real money: the application treats payments as unavailable in production
while this is the configured provider.
"""

import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from app.providers.payments.base import (
    InitiationResult,
    InvalidSignatureError,
    ProviderError,
    ProviderStatus,
    RefundResult,
    WebhookEvent,
)

SIGNATURE_HEADER = "x-fake-signature"


@dataclass
class _Record:
    amount_ugx: int
    status: str = "PENDING"
    refunded: int = 0


def sign(secret: bytes, body: bytes, timestamp: int | None = None) -> str:
    """The header value the fake provider attaches: t=<unix>,v1=<hex hmac of "t.body">."""
    ts = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        webhook_secret: bytes,
        *,
        tolerance_seconds: int = 300,
        checkout_base: str = "/pay/fake",
    ) -> None:
        self._secret = webhook_secret
        self._tolerance = tolerance_seconds
        self._checkout_base = checkout_base
        self._payments: dict[str, _Record] = {}
        self._by_idempotency: dict[str, str] = {}
        self.fail_next_initiate = False  # test hook: simulate a provider outage
        self.fail_verify = False

    # ---- PaymentProvider
    def initiate(
        self, *, payment_id: str, amount_ugx: int, currency: str, description: str,
        return_url: str, idempotency_key: str,
    ) -> InitiationResult:  # fmt: skip
        if self.fail_next_initiate:
            self.fail_next_initiate = False
            raise ProviderError("fake provider outage")
        if (
            idempotency_key in self._by_idempotency
        ):  # same key -> same payment, never a duplicate charge
            ref = self._by_idempotency[idempotency_key]
        else:
            ref = f"fake_{uuid.uuid4().hex[:16]}"
            self._payments[ref] = _Record(amount_ugx=amount_ugx)
            self._by_idempotency[idempotency_key] = ref
        return InitiationResult(
            provider_reference=ref, checkout_url=f"{self._checkout_base}/{payment_id}"
        )

    def verify(self, provider_reference: str) -> ProviderStatus:
        if self.fail_verify:
            raise ProviderError("fake provider outage")
        record = self._payments.get(provider_reference)
        if record is None:
            raise ProviderError("unknown payment")
        return ProviderStatus(
            status=record.status,
            provider_reference=provider_reference,
            amount_ugx=record.amount_ugx,
        )  # type: ignore[arg-type]

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        header = {k.lower(): v for k, v in headers.items()}.get(SIGNATURE_HEADER)
        if not header:
            raise InvalidSignatureError("missing signature")
        try:
            parts = dict(item.split("=", 1) for item in header.split(","))
            timestamp, provided = int(parts["t"]), parts["v1"]
        except (KeyError, ValueError) as exc:
            raise InvalidSignatureError("malformed signature") from exc
        if abs(time.time() - timestamp) > self._tolerance:
            raise InvalidSignatureError("stale timestamp")  # replayed old webhooks are rejected
        expected = hmac.new(
            self._secret, f"{timestamp}.".encode() + body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, provided):
            raise InvalidSignatureError("bad signature")
        try:
            data = json.loads(body)
            return WebhookEvent(
                event_id=str(data["id"]), event_type=str(data["type"]),
                provider_reference=str(data["reference"]), payload=data,
            )  # fmt: skip
        except (KeyError, ValueError, TypeError) as exc:
            raise InvalidSignatureError("malformed body") from exc

    def refund(
        self, *, provider_reference: str, amount_ugx: int, reason: str, idempotency_key: str
    ) -> RefundResult:
        record = self._payments.get(provider_reference)
        if record is None or record.status != "PAID":
            return RefundResult(provider_reference=f"re_{uuid.uuid4().hex[:12]}", status="FAILED")
        record.refunded += amount_ugx
        return RefundResult(provider_reference=f"re_{idempotency_key[:12]}", status="SUCCEEDED")

    # ---- test / development helpers (not part of the PaymentProvider interface)
    def set_status(self, provider_reference: str, status: str) -> None:
        self._payments[provider_reference].status = status

    def signed_webhook(
        self, event_id: str, event_type: str, reference: str, *, timestamp: int | None = None
    ) -> tuple[bytes, dict[str, str]]:
        body = json.dumps({"id": event_id, "type": event_type, "reference": reference}).encode()
        return body, {"X-Fake-Signature": sign(self._secret, body, timestamp)}
