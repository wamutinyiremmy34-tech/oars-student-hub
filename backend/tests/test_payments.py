"""Payments: creation, the webhook pipeline, idempotency, refunds and premium purchases (FakeProvider)."""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import (
    PrintCampus,
    auth_headers,
    fake_provider,
    make_resource,
    make_user,
    new_order,
    op,
    pickup_code_for,
    run_to_ready,
    v1,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog
from app.modules.payments.models import Payment, PaymentEvent, PaymentTransaction, Refund
from app.modules.printing.models import OrderStatusHistory, PrintOrder
from app.modules.resources.models import Entitlement
from app.providers.payments.fake import FakeProvider

pytestmark = pytest.mark.integration

WEBHOOK = v1("/payments/webhooks/fake")


@pytest.fixture
def campus(db: Session) -> PrintCampus:
    return PrintCampus(db)


def U(value) -> uuid.UUID:  # type: ignore[no-untyped-def]
    return uuid.UUID(str(value))


def pay(client: TestClient, user, *, key: str | None = None, **target):  # type: ignore[no-untyped-def]
    headers = {**auth_headers(user), **({"Idempotency-Key": key} if key else {})}
    return client.post(v1("/payments"), json=target, headers=headers)


def deliver(
    client: TestClient, event_id: str, reference: str, event_type: str = "payment.succeeded", **kw
):  # type: ignore[no-untyped-def]
    body, headers = fake_provider(client).signed_webhook(event_id, event_type, reference, **kw)
    return client.post(WEBHOOK, content=body, headers=headers)


def count(db: Session, model, *where) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def online_order(client, c: PrintCampus, pages: int = 2) -> dict:  # type: ignore[no-untyped-def,type-arg]
    return new_order(client, c.student, c.shop, pages=pages, method="ONLINE")  # UGX 50 per page


def start_payment(client, c: PrintCampus, db: Session, pages: int = 2):  # type: ignore[no-untyped-def]
    order = online_order(client, c, pages)
    created = pay(client, c.student, order_id=order["id"])
    assert created.status_code == 201, created.text
    return order, db.get(Payment, U(created.json()["data"]["id"]))


def paid_order(client, c: PrintCampus, db: Session, pages: int = 2):  # type: ignore[no-untyped-def]
    order, payment = start_payment(client, c, db, pages)
    fake_provider(client).set_status(payment.provider_reference, "PAID")
    assert (
        deliver(client, f"evt-{uuid.uuid4().hex}", payment.provider_reference).json()["data"][
            "status"
        ]
        == "PROCESSED"
    )
    db.refresh(payment)
    return order, payment


# --------------------------------------------------------------------------- creating payments


def test_online_payment_availability_is_reported(api_client: TestClient) -> None:
    assert api_client.get(v1("/payments/config")).json()["data"] == {
        "online_available": True,
        "provider": "fake",
    }


def test_the_payment_amount_always_comes_from_the_server(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    order = online_order(api_client, campus, pages=2)
    assert order["awaiting_payment"] is True
    response = pay(
        api_client, campus.student, order_id=order["id"], amount_ugx=1, amount=1
    )  # smuggled amounts are ignored
    assert response.status_code == 201
    data = response.json()["data"]
    assert (data["amount_ugx"], data["status"], data["purpose"], data["currency"]) == (
        100,
        "PENDING",
        "PRINT_ORDER",
        "UGX",
    )
    assert data["checkout_url"] == f"/pay/fake/{data['id']}"
    assert db.get(PrintOrder, U(order["id"])).payment_status == "PENDING"
    assert db.scalars(select(PaymentTransaction.kind)).all() == [
        "INITIATE"
    ]  # every provider call is logged


def test_only_the_owner_can_pay_and_only_for_payable_online_orders(
    api_client: TestClient, campus: PrintCampus
) -> None:
    c, client = campus, api_client
    order = online_order(client, c)
    assert pay(client, c.student2, order_id=order["id"]).status_code == 404  # someone else's order
    assert pay(client, c.operator, order_id=order["id"]).status_code == 403  # no payment:create
    assert client.post(v1("/payments"), json={"order_id": order["id"]}).status_code == 401
    assert (
        pay(client, c.student, order_id=order["id"], resource_id=str(uuid.uuid4())).status_code
        == 422
    )
    assert pay(client, c.student).status_code == 422  # exactly one target

    cash = new_order(client, c.student2, c.shop, pages=1)
    refused = pay(client, c.student2, order_id=cash["id"])
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "not_online_order")

    client.post(v1(f"/print/orders/{order['id']}/cancel"), json={}, headers=auth_headers(c.student))
    closed = pay(client, c.student, order_id=order["id"])
    assert (closed.status_code, closed.json()["error"]["code"]) == (409, "order_not_payable")


def test_an_unpaid_online_order_cannot_bypass_payment(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order = online_order(client, c)
    for action in ("accept", "printing", "ready"):
        assert op(client, c.operator, order["id"], action).status_code == 409
    assert (
        op(client, c.operator, order["id"], "accept").json()["error"]["code"] == "payment_required"
    )
    assert db.get(PrintOrder, U(order["id"])).status == "SUBMITTED"


# --------------------------------------------------------------------------- the webhook pipeline


def test_a_verified_webhook_marks_the_payment_paid_and_unblocks_the_order(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order, payment = start_payment(client, c, db)
    fake_provider(client).set_status(payment.provider_reference, "PAID")

    response = deliver(client, "evt-1", payment.provider_reference)
    assert response.status_code == 200 and response.json()["data"]["status"] == "PROCESSED"
    db.refresh(payment)
    assert payment.status == "PAID" and payment.paid_at is not None
    seen = client.get(v1(f"/print/orders/{order['id']}"), headers=auth_headers(c.student)).json()[
        "data"
    ]
    assert (seen["payment_status"], seen["awaiting_payment"], seen["payment"]["status"]) == (
        "PAID",
        False,
        "PAID",
    )

    assert op(client, c.operator, order["id"], "accept").status_code == 200
    assert [op(client, c.operator, order["id"], a).status_code for a in ("printing", "ready")] == [
        200,
        200,
    ]
    event = db.scalar(select(PaymentEvent))
    assert (event.provider_event_id, event.processing_status, event.payment_id) == (
        "evt-1",
        "PROCESSED",
        payment.id,
    )
    assert db.scalars(
        select(PaymentTransaction.kind).order_by(PaymentTransaction.created_at)
    ).all() == ["INITIATE", "VERIFY"]
    assert "payment.paid" in db.scalars(select(AuditLog.action)).all()


def test_a_webhook_alone_is_not_proof_of_payment(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    order, payment = start_payment(api_client, campus, db)
    # The body CLAIMS success, but the provider still says PENDING, so we do not believe it.
    assert (
        deliver(api_client, "evt-liar", payment.provider_reference).json()["data"]["status"]
        == "IGNORED"
    )
    db.refresh(payment)
    assert payment.status == "PENDING"
    assert db.get(PrintOrder, U(order["id"])).payment_status == "PENDING"


def test_forged_unsigned_and_stale_webhooks_are_rejected(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    _, payment = start_payment(api_client, campus, db)
    ref = payment.provider_reference
    fake_provider(api_client).set_status(ref, "PAID")  # even though the provider says paid

    body, headers = fake_provider(api_client).signed_webhook("evt-1", "payment.succeeded", ref)
    other_secret = FakeProvider(b"x" * 32).signed_webhook("evt-1", "payment.succeeded", ref)[1]
    attempts = {
        "tampered body": api_client.post(
            WEBHOOK, content=body.replace(b"succeeded", b"failed"), headers=headers
        ),
        "no signature": api_client.post(WEBHOOK, content=body),
        "garbage signature": api_client.post(
            WEBHOOK, content=body, headers={"X-Fake-Signature": "t=1,v1=abc"}
        ),
        "wrong secret": api_client.post(WEBHOOK, content=body, headers=other_secret),
        "stale": deliver(api_client, "evt-2", ref, timestamp=int(time.time()) - 3600),
    }
    for name, response in attempts.items():
        assert response.status_code == 401, name
        assert response.json()["error"]["code"] == "invalid_signature", name
    assert count(db, PaymentEvent) == 0  # nothing from an unverified sender is stored
    db.refresh(payment)
    assert payment.status == "PENDING"


def test_duplicate_and_replayed_webhooks_are_harmless(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    _, payment = start_payment(client, c, db)
    ref = payment.provider_reference
    fake_provider(client).set_status(ref, "PAID")

    first = deliver(client, "evt-1", ref).json()["data"]["status"]
    db.refresh(payment)
    paid_at = payment.paid_at
    replay = deliver(client, "evt-1", ref).json()["data"]["status"]  # exact same event id (a retry)
    other_id = deliver(client, "evt-2", ref).json()["data"][
        "status"
    ]  # the provider re-sends under a new id
    assert (first, replay, other_id) == ("PROCESSED", "DUPLICATE", "IGNORED")

    db.refresh(payment)
    assert payment.paid_at == paid_at
    assert (
        count(db, Payment) == 1 and count(db, PaymentEvent) == 2
    )  # evt-1 once, evt-2 recorded as a no-op
    assert count(db, AuditLog, AuditLog.action == "payment.paid") == 1
    assert count(db, OrderStatusHistory) == 1  # no extra order transitions
    assert count(db, PaymentTransaction, PaymentTransaction.kind == "VERIFY") == 2


def test_webhooks_for_unknown_payments_and_providers(api_client: TestClient, db: Session) -> None:
    response = deliver(api_client, "evt-x", "fake_does_not_exist")
    assert response.status_code == 200 and response.json()["data"]["status"] == "IGNORED"
    event = db.scalar(select(PaymentEvent))
    assert event.payment_id is None and event.note == "unknown_payment"
    assert api_client.post(v1("/payments/webhooks/stripe"), content=b"{}").status_code == 404


def test_an_amount_mismatch_is_never_marked_paid(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    _, payment = start_payment(api_client, campus, db)
    provider = fake_provider(api_client)
    provider.set_status(payment.provider_reference, "PAID")
    provider._payments[
        payment.provider_reference
    ].amount_ugx = 1  # the provider reports a different amount
    assert (
        deliver(api_client, "evt-1", payment.provider_reference).json()["data"]["status"]
        == "IGNORED"
    )
    db.refresh(payment)
    assert payment.status == "PENDING"
    assert "payment.amount_mismatch" in db.scalars(select(AuditLog.action)).all()


def test_a_provider_outage_during_verification_lets_the_webhook_be_retried(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    _, payment = start_payment(api_client, campus, db)
    ref = payment.provider_reference
    provider = fake_provider(api_client)
    provider.set_status(ref, "PAID")
    provider.fail_verify = True
    down = deliver(api_client, "evt-1", ref)
    assert (down.status_code, down.json()["error"]["code"]) == (503, "verification_unavailable")
    assert (
        count(db, PaymentEvent) == 0
    )  # rolled back, so the provider's retry is not mistaken for a duplicate

    provider.fail_verify = False
    assert deliver(api_client, "evt-1", ref).json()["data"]["status"] == "PROCESSED"
    db.refresh(payment)
    assert payment.status == "PAID"


# --------------------------------------------------------------------------- idempotency, retries, expiry


def test_idempotency_key_and_resume_prevent_duplicate_payments(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order = online_order(client, c)
    first = pay(client, c.student, key="pay-key-0001", order_id=order["id"]).json()["data"]["id"]
    again = pay(client, c.student, key="pay-key-0001", order_id=order["id"]).json()["data"]["id"]
    resumed = pay(client, c.student, order_id=order["id"]).json()["data"][
        "id"
    ]  # no key: the open checkout is resumed
    assert first == again == resumed and count(db, Payment) == 1

    other = online_order(client, c)
    clash = pay(client, c.student, key="pay-key-0001", order_id=other["id"])
    assert (clash.status_code, clash.json()["error"]["code"]) == (409, "idempotency_key_reuse")


def test_a_provider_outage_when_starting_a_payment_is_recoverable(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    order = online_order(api_client, campus)
    fake_provider(api_client).fail_next_initiate = True
    down = pay(api_client, campus.student, order_id=order["id"])
    assert (down.status_code, down.json()["error"]["code"]) == (503, "provider_unavailable")
    failed = db.scalar(select(Payment))
    assert (failed.status, failed.failure_reason) == ("FAILED", "provider_unavailable")
    assert db.get(PrintOrder, U(order["id"])).payment_status == "FAILED"

    retry = pay(api_client, campus.student, order_id=order["id"])
    assert retry.status_code == 201 and retry.json()["data"]["status"] == "PENDING"
    assert count(db, Payment) == 2


def test_abandoned_checkouts_expire_and_a_late_confirmation_is_still_honoured(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order, old = start_payment(client, c, db)
    old.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    new_id = pay(client, c.student, order_id=order["id"]).json()["data"]["id"]
    assert new_id != str(old.id)
    db.refresh(old)
    assert (old.status, old.failure_reason) == ("FAILED", "expired")

    # The student actually completed the FIRST checkout late. The money was taken, so it must count.
    fake_provider(client).set_status(old.provider_reference, "PAID")
    assert (
        deliver(client, "evt-late", old.provider_reference).json()["data"]["status"] == "PROCESSED"
    )
    newer = db.get(Payment, U(new_id))
    db.refresh(old)
    db.refresh(newer)
    assert (old.status, newer.status, newer.failure_reason) == (
        "PAID",
        "FAILED",
        "superseded_by_confirmed_payment",
    )
    assert db.get(PrintOrder, U(order["id"])).payment_status == "PAID"


def test_owners_can_re_check_a_payment_when_the_webhook_is_late(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    order, payment = start_payment(api_client, campus, db)
    url = v1(f"/payments/{payment.id}/verify")
    assert (
        api_client.post(url, headers=auth_headers(campus.student)).json()["data"]["status"]
        == "PENDING"
    )
    fake_provider(api_client).set_status(payment.provider_reference, "PAID")
    assert api_client.post(url, headers=auth_headers(campus.student2)).status_code == 404
    assert (
        api_client.post(url, headers=auth_headers(campus.student)).json()["data"]["status"]
        == "PAID"
    )
    assert db.get(PrintOrder, U(order["id"])).payment_status == "PAID"
    assert (
        api_client.get(
            v1(f"/payments/{payment.id}"), headers=auth_headers(campus.student2)
        ).status_code
        == 404
    )
    assert (
        api_client.get(
            v1(f"/payments/{payment.id}"), headers=auth_headers(campus.student)
        ).status_code
        == 200
    )


def test_online_orders_complete_the_whole_workflow_once_paid(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order, _ = paid_order(client, c, db)
    run_to_ready(client, c.operator, order["id"])
    done = op(
        client, c.operator, order["id"], "complete", {"pickup_code": pickup_code_for(order["id"])}
    )
    assert done.status_code == 200 and done.json()["data"]["status"] == "COMPLETED"
    assert count(db, Payment) == 1  # no cash record for an online order


# --------------------------------------------------------------------------- refunds


def test_cancelling_a_paid_order_queues_a_refund_that_staff_process_once(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order, payment = paid_order(client, c, db)
    refund_url = v1(f"/payments/{payment.id}/refund")
    assert (
        client.post(refund_url, headers=auth_headers(c.admin)).json()["error"]["code"]
        == "order_still_active"
    )

    assert (
        client.post(
            v1(f"/print/orders/{order['id']}/cancel"), json={}, headers=auth_headers(c.student)
        ).status_code
        == 200
    )
    queued = db.scalar(select(Refund))
    assert (queued.status, queued.amount_ugx, queued.payment_id) == ("REQUESTED", 100, payment.id)

    assert client.post(refund_url, headers=auth_headers(c.operator)).status_code == 403
    assert client.post(refund_url, headers=auth_headers(c.admin_b)).status_code == 404
    done = client.post(refund_url, headers=auth_headers(c.admin))
    assert done.status_code == 200 and done.json()["data"]["status"] == "SUCCEEDED"
    db.refresh(payment)
    assert (
        payment.status == "REFUNDED"
        and db.get(PrintOrder, U(order["id"])).payment_status == "REFUNDED"
    )
    assert (
        client.post(refund_url, headers=auth_headers(c.admin)).json()["error"]["code"]
        == "not_refundable"
    )  # only once
    assert count(db, Refund) == 1


def test_a_rejected_paid_order_is_refundable(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    order, payment = paid_order(api_client, campus, db)
    assert (
        op(
            api_client, campus.operator, order["id"], "reject", {"reason": "Cannot print this file"}
        ).status_code
        == 200
    )
    assert db.scalar(select(Refund)).status == "REQUESTED"
    assert (
        api_client.post(
            v1(f"/payments/{payment.id}/refund"), headers=auth_headers(campus.platform)
        ).json()["data"]["status"]
        == "SUCCEEDED"
    )


def test_cancelling_during_checkout_stops_the_payment_and_a_late_payment_is_refunded(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order, payment = start_payment(client, c, db)
    client.post(v1(f"/print/orders/{order['id']}/cancel"), json={}, headers=auth_headers(c.student))
    db.refresh(payment)
    assert (payment.status, payment.failure_reason) == ("FAILED", "order_closed")

    fake_provider(client).set_status(
        payment.provider_reference, "PAID"
    )  # the student paid anyway, a moment too late
    assert (
        deliver(client, "evt-1", payment.provider_reference).json()["data"]["status"] == "PROCESSED"
    )
    db.refresh(payment)
    assert (
        payment.status == "PAID" and db.scalar(select(Refund)).status == "REQUESTED"
    )  # the money is not kept


def test_cash_payments_are_not_refunded_through_the_provider(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order = new_order(client, c.student, c.shop, pages=1)
    run_to_ready(client, c.operator, order["id"])
    op(client, c.operator, order["id"], "payment", {"amount_ugx": 50})
    op(client, c.operator, order["id"], "complete", {"pickup_code": pickup_code_for(order["id"])})
    cash = db.scalar(select(Payment))
    assert (
        client.post(v1(f"/payments/{cash.id}/refund"), headers=auth_headers(c.admin)).json()[
            "error"
        ]["code"]
        == "cash_refund_manual"
    )


# --------------------------------------------------------------------------- premium resources


@pytest.fixture
def premium(db: Session, campus: PrintCampus, storage):  # type: ignore[no-untyped-def]
    provider = make_user(db, roles=[("RESOURCE_PROVIDER", campus.inst.id)])
    return make_resource(
        db,
        provider=provider,
        institution=campus.inst,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
        price=5000,
    ), provider


def download(client: TestClient, user, rid):  # type: ignore[no-untyped-def]
    return client.post(v1(f"/resources/{rid}/download"), headers=auth_headers(user))


def test_buying_a_premium_resource_grants_access_exactly_once(
    api_client: TestClient, campus: PrintCampus, premium, db: Session
) -> None:
    c, client = campus, api_client
    resource, _ = premium
    assert download(client, c.student, resource.id).status_code == 403

    created = pay(client, c.student, resource_id=str(resource.id)).json()["data"]
    assert (created["amount_ugx"], created["purpose"]) == (5000, "RESOURCE_PURCHASE")
    payment = db.get(Payment, U(created["id"]))
    assert download(client, c.student, resource.id).status_code == 403  # pending is not paid

    fake_provider(client).set_status(payment.provider_reference, "PAID")
    for event_id in ("evt-1", "evt-1", "evt-2"):  # duplicates and re-sends
        deliver(client, event_id, payment.provider_reference)
    entitlement = db.scalar(select(Entitlement))
    assert (entitlement.status, entitlement.source, entitlement.source_reference) == (
        "ACTIVE",
        "PURCHASE",
        str(payment.id),
    )
    assert (
        count(db, Entitlement) == 1
        and count(db, AuditLog, AuditLog.action == "entitlement.granted") == 1
    )
    assert download(client, c.student, resource.id).status_code == 200
    assert download(client, c.student2, resource.id).status_code == 403  # access is per buyer

    again = pay(client, c.student, resource_id=str(resource.id))
    assert (again.status_code, again.json()["error"]["code"]) == (409, "already_entitled")


def test_purchase_rules(
    api_client: TestClient, campus: PrintCampus, premium, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    c, client = campus, api_client
    resource, provider = premium
    free = make_resource(
        db, provider=provider, institution=c.inst, storage=storage, status="PUBLISHED"
    )
    draft = make_resource(
        db, provider=provider, institution=c.inst, storage=storage, status="DRAFT", access="PREMIUM"
    )
    assert pay(client, c.student, resource_id=str(free.id)).status_code == 404  # nothing to buy
    assert (
        pay(client, c.student, resource_id=str(draft.id)).status_code == 404
    )  # unpublished does not exist for buyers
    assert (
        pay(client, provider, resource_id=str(resource.id)).status_code == 403
    )  # no payment:create
    assert pay(client, c.student, resource_id=str(uuid.uuid4())).status_code == 404


def test_refunding_a_purchase_revokes_access(
    api_client: TestClient, campus: PrintCampus, premium, db: Session
) -> None:
    c, client = campus, api_client
    resource, _ = premium
    payment = db.get(
        Payment, U(pay(client, c.student, resource_id=str(resource.id)).json()["data"]["id"])
    )
    fake_provider(client).set_status(payment.provider_reference, "PAID")
    deliver(client, "evt-1", payment.provider_reference)
    assert download(client, c.student, resource.id).status_code == 200

    assert (
        client.post(
            v1(f"/payments/{payment.id}/refund"), headers=auth_headers(c.admin_b)
        ).status_code
        == 404
    )
    assert (
        client.post(v1(f"/payments/{payment.id}/refund"), headers=auth_headers(c.admin)).status_code
        == 200
    )
    assert download(client, c.student, resource.id).status_code == 403
    assert db.scalar(select(Entitlement)).status == "REVOKED"


# --------------------------------------------------------------------------- development simulator


def test_the_development_simulator_drives_the_real_pipeline(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    _, payment = start_payment(client, c, db)
    body = {"payment_id": str(payment.id), "outcome": "success"}
    assert (
        client.post(
            v1("/payments/dev/simulate"), json=body, headers=auth_headers(c.student2)
        ).status_code
        == 404
    )  # not yours
    done = client.post(v1("/payments/dev/simulate"), json=body, headers=auth_headers(c.student))
    assert done.json()["data"]["status"] == "PROCESSED"
    db.refresh(payment)
    assert (
        payment.status == "PAID" and count(db, PaymentEvent) == 1
    )  # it went through signature check + dedupe + verify

    failing_order = online_order(client, c)
    failing = db.get(
        Payment, U(pay(client, c.student, order_id=failing_order["id"]).json()["data"]["id"])
    )
    client.post(
        v1("/payments/dev/simulate"),
        json={"payment_id": str(failing.id), "outcome": "failure"},
        headers=auth_headers(c.student),
    )
    db.refresh(failing)
    assert failing.status == "FAILED"
    assert db.get(PrintOrder, U(failing_order["id"])).payment_status == "FAILED"
