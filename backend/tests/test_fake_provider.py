"""FakeProvider: signing, replay protection and the provider contract (pure unit tests)."""

import json
import time

import pytest

from app.providers.payments.base import InvalidSignatureError, ProviderError
from app.providers.payments.fake import FakeProvider, sign

SECRET = b"unit-test-webhook-secret-0123456789"


def provider() -> FakeProvider:
    return FakeProvider(SECRET, tolerance_seconds=300)


def init(p: FakeProvider, key: str = "k1", amount: int = 5000):  # type: ignore[no-untyped-def]
    return p.initiate(
        payment_id="pay-1",
        amount_ugx=amount,
        currency="UGX",
        description="d",
        return_url="/x",
        idempotency_key=key,
    )


def test_initiate_is_idempotent_per_key() -> None:
    p = provider()
    first, again, other = init(p, "k1"), init(p, "k1"), init(p, "k2")
    assert first.provider_reference == again.provider_reference != other.provider_reference
    assert first.checkout_url == "/pay/fake/pay-1"


def test_verify_reports_the_authoritative_state() -> None:
    p = provider()
    ref = init(p).provider_reference
    assert p.verify(ref).status == "PENDING"
    p.set_status(ref, "PAID")
    status = p.verify(ref)
    assert (status.status, status.amount_ugx) == ("PAID", 5000)
    with pytest.raises(ProviderError):
        p.verify("fake_unknown")


def test_webhook_roundtrip() -> None:
    p = provider()
    ref = init(p).provider_reference
    body, headers = p.signed_webhook("evt-1", "payment.succeeded", ref)
    event = p.parse_webhook(headers, body)
    assert (event.event_id, event.event_type, event.provider_reference) == (
        "evt-1",
        "payment.succeeded",
        ref,
    )
    assert (
        p.parse_webhook({k.lower(): v for k, v in headers.items()}, body).event_id == "evt-1"
    )  # header case-insensitive


def test_tampered_bodies_and_wrong_secrets_are_rejected() -> None:
    p = provider()
    body, headers = p.signed_webhook("evt-1", "payment.succeeded", "ref")
    forged = json.dumps({"id": "evt-1", "type": "payment.succeeded", "reference": "OTHER"}).encode()
    with pytest.raises(InvalidSignatureError):
        p.parse_webhook(headers, forged)
    with pytest.raises(InvalidSignatureError):
        FakeProvider(b"a-different-secret-entirely-xxxxxxxx").parse_webhook(headers, body)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Fake-Signature": ""},
        {"X-Fake-Signature": "garbage"},
        {"X-Fake-Signature": "t=abc,v1=00"},
        {"X-Fake-Signature": "t=1"},
    ],
)
def test_missing_or_malformed_signatures_are_rejected(headers: dict[str, str]) -> None:
    with pytest.raises(InvalidSignatureError):
        provider().parse_webhook(headers, b"{}")


def test_stale_timestamps_are_rejected_so_old_webhooks_cannot_be_replayed() -> None:
    p = provider()
    old = int(time.time()) - 3600
    body, headers = p.signed_webhook("evt-1", "payment.succeeded", "ref", timestamp=old)
    with pytest.raises(InvalidSignatureError):
        p.parse_webhook(headers, body)
    future = int(time.time()) + 3600
    body, headers = p.signed_webhook("evt-2", "payment.succeeded", "ref", timestamp=future)
    with pytest.raises(InvalidSignatureError):
        p.parse_webhook(headers, body)


def test_correctly_signed_but_malformed_bodies_are_rejected() -> None:
    body = b"not json"
    with pytest.raises(InvalidSignatureError):
        provider().parse_webhook({"X-Fake-Signature": sign(SECRET, body)}, body)
    body = json.dumps({"id": "x"}).encode()  # missing type/reference
    with pytest.raises(InvalidSignatureError):
        provider().parse_webhook({"X-Fake-Signature": sign(SECRET, body)}, body)


def test_refunds_only_succeed_for_paid_payments() -> None:
    p = provider()
    ref = init(p).provider_reference
    assert (
        p.refund(provider_reference=ref, amount_ugx=5000, reason="r", idempotency_key="i1").status
        == "FAILED"
    )
    p.set_status(ref, "PAID")
    assert (
        p.refund(provider_reference=ref, amount_ugx=5000, reason="r", idempotency_key="i2").status
        == "SUCCEEDED"
    )


def test_a_provider_outage_surfaces_as_a_retryable_error() -> None:
    p = provider()
    p.fail_next_initiate = True
    with pytest.raises(ProviderError):
        init(p)
    assert init(p).provider_reference  # the outage was transient
    p.fail_verify = True
    with pytest.raises(ProviderError):
        p.verify("anything")
