"""Payment provider abstraction. The rest of the application depends ONLY on this module.

A real Ugandan provider or aggregator is added by implementing PaymentProvider and registering it in
factory.py; nothing else changes. The API never trusts a provider webhook body on its own:
the service re-verifies the payment with verify() before changing any state.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

ProviderPaymentStatus = Literal["PENDING", "PAID", "FAILED"]


class InvalidSignatureError(Exception):
    """The webhook was not signed by the provider (wrong signature, stale timestamp, or malformed)."""


class ProviderError(Exception):
    """The provider could not be reached or rejected the request. Safe to retry."""


@dataclass(frozen=True)
class InitiationResult:
    provider_reference: str
    checkout_url: str


@dataclass(frozen=True)
class ProviderStatus:
    status: ProviderPaymentStatus
    provider_reference: str
    amount_ugx: int | None = None


@dataclass(frozen=True)
class WebhookEvent:
    event_id: str  # unique per provider; used for de-duplication
    event_type: str
    provider_reference: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RefundResult:
    provider_reference: str
    status: Literal["SUCCEEDED", "FAILED"]


class PaymentProvider(Protocol):
    name: str

    def initiate(
        self, *, payment_id: str, amount_ugx: int, currency: str, description: str,
        return_url: str, idempotency_key: str,
    ) -> InitiationResult: ...  # fmt: skip

    def verify(self, provider_reference: str) -> ProviderStatus:
        """Ask the provider for the authoritative state of a payment."""
        ...

    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent:
        """Verify the signature and parse the event. Raises InvalidSignatureError. Never trusts unsigned input."""
        ...

    def refund(
        self, *, provider_reference: str, amount_ugx: int, reason: str, idempotency_key: str
    ) -> RefundResult: ...  # fmt: skip
