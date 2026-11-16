"""Payments.

Trust model: a webhook body is only a *hint to go and ask the provider*. State changes come from
provider.verify(), never from the webhook payload and never from the frontend.

Flow: signature check -> de-duplicate on (provider, event id) -> re-verify with the provider ->
ONE database transaction that marks the payment PAID and grants the entitlement / advances the order.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from app.core.http import RequestMeta
from app.modules.audit import service as audit
from app.modules.audit.service import scrub
from app.modules.payments.models import Payment, PaymentEvent, PaymentTransaction, Refund
from app.modules.printing.models import PrintOrder
from app.modules.printing.state import (
    OrderStatus,
    PaymentStatus,
    can_order_pay_transition,
    can_pay_transition,
)
from app.modules.rbac.principal import Principal
from app.modules.resources import access
from app.modules.resources.models import AccessType, Entitlement, Resource, ResourceStatus
from app.providers.payments.base import (
    InvalidSignatureError,
    PaymentProvider,
    ProviderError,
    ProviderStatus,
)
from app.providers.payments.fake import FakeProvider

logger = logging.getLogger(__name__)
P = PaymentStatus


def _now() -> datetime:
    return datetime.now(UTC)


def fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def record_transaction(
    db: Session, payment: Payment, kind: str, outcome: str, *,
    reference: str | None = None, amount: int | None = None, detail: dict[str, Any] | None = None,
) -> None:  # fmt: skip
    db.add(
        PaymentTransaction(
            payment_id=payment.id, kind=kind, outcome=outcome, provider_reference=reference,
            amount_ugx=amount, detail=scrub(detail) if detail else None,
        )
    )  # fmt: skip


def payment_institution_id(db: Session, payment: Payment) -> uuid.UUID:
    if payment.print_order_id is not None:
        order = db.get(PrintOrder, payment.print_order_id)
        assert order is not None
        return order.institution_id
    resource = db.get(Resource, payment.resource_id)
    assert resource is not None
    return resource.institution_id


def _set_order_payment_status(order: PrintOrder, target: str) -> bool:
    if can_order_pay_transition(order.payment_status, target):
        order.payment_status = target
        return True
    return False


# --------------------------------------------------------------------------- failing / paying


def _fail(db: Session, payment: Payment, reason: str) -> None:
    if not can_pay_transition(payment.status, P.FAILED):
        return
    payment.status = P.FAILED
    payment.failed_at = _now()
    payment.failure_reason = reason
    if payment.print_order_id is not None:
        order = db.get(PrintOrder, payment.print_order_id)
        if order is not None and order.payment_status == P.PENDING:
            _set_order_payment_status(order, P.FAILED)


def request_refund(
    db: Session, payment: Payment, reason: str, actor_id: uuid.UUID | None
) -> Refund | None:
    """Queue a refund for staff to process. Idempotent: at most one open or completed refund per payment
    (also enforced by a partial unique index)."""
    if payment.status != P.PAID or payment.provider == "CASH":
        return None
    existing = db.scalar(
        select(Refund).where(
            Refund.payment_id == payment.id, Refund.status.in_(("REQUESTED", "SUCCEEDED"))
        )
    )
    if existing is not None:
        return existing
    refund = Refund(
        payment_id=payment.id,
        amount_ugx=payment.amount_ugx,
        reason=reason[:255],
        requested_by_user_id=actor_id,
    )
    db.add(refund)
    db.flush()
    audit.record(db, action="refund.requested", actor_user_id=actor_id, target_type="payment",
                 target_id=str(payment.id), details={"reason": reason}, institution_id=payment_institution_id(db, payment))  # fmt: skip
    return refund


def settle_closed_order(
    db: Session, order: PrintOrder, reason: str, actor_id: uuid.UUID | None
) -> None:
    """An online order was cancelled or rejected: stop a pending payment, or queue a refund for a paid one."""
    if order.payment_method != "ONLINE":
        return
    payment = db.scalar(
        select(Payment).where(Payment.print_order_id == order.id, Payment.status.in_((P.PENDING, P.PAID)))
        .order_by(Payment.created_at.desc()).limit(1).with_for_update()
    )  # fmt: skip
    if payment is None:
        return
    if payment.status == P.PENDING:
        _fail(db, payment, "order_closed")
    else:
        request_refund(db, payment, reason, actor_id)


def _on_paid(db: Session, payment: Payment, meta: RequestMeta | None) -> None:
    if payment.print_order_id is not None:
        order = db.scalar(
            select(PrintOrder).where(PrintOrder.id == payment.print_order_id).with_for_update()
        )
        assert order is not None
        _set_order_payment_status(order, P.PAID)
        if order.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
            # Money arrived for an order that is already closed: do not keep it, queue the refund.
            request_refund(db, payment, "Payment received after the order was closed", None)
    else:
        resource = db.get(Resource, payment.resource_id)
        assert resource is not None
        access.grant_entitlement(  # idempotent upsert, inside THIS transaction
            db, resource=resource, user_id=payment.payer_user_id, source="PURCHASE",
            reference=str(payment.id), expires_at=None, granted_by=None, meta=meta, commit=False,
        )  # fmt: skip


def _claim_target(
    db: Session, payment: Payment, meta: RequestMeta | None, institution_id: uuid.UUID
) -> bool:
    """Before this payment becomes PAID, retire any OTHER live attempt for the same order/resource, because
    the database allows only one live (pending or paid) payment per target. If the target was already paid
    by a different payment, this one is a duplicate charge: it is NOT applied and is flagged for a manual refund."""
    if payment.print_order_id is not None:
        same_target = (Payment.print_order_id == payment.print_order_id,)
    else:
        same_target = (
            Payment.payer_user_id == payment.payer_user_id,
            Payment.resource_id == payment.resource_id,
        )
    others = db.scalars(
        select(Payment)
        .where(*same_target, Payment.id != payment.id, Payment.status.in_((P.PENDING, P.PAID)))
        .with_for_update()
    ).all()
    if any(o.status == P.PAID for o in others):
        audit.record(db, action="payment.duplicate_paid_needs_refund", outcome="DENIED", target_type="payment",
                     target_id=str(payment.id), institution_id=institution_id, meta=meta)  # fmt: skip
        logger.error("duplicate_payment_confirmed", extra={"payment_id": str(payment.id)})
        return False
    for other in others:  # a newer attempt is superseded by the one the customer actually completed
        _fail(db, other, "superseded_by_confirmed_payment")
    db.flush()
    return True


def apply_provider_status(
    db: Session, payment: Payment, status: ProviderStatus, *, source: str, meta: RequestMeta | None
) -> str:
    """Apply the provider's authoritative state. The caller holds a row lock on `payment`.
    Returns PAID, FAILED, MISMATCH or NOOP. Safe to call repeatedly with the same input."""
    institution_id = payment_institution_id(db, payment)
    if status.status == "PAID":
        if status.amount_ugx is not None and status.amount_ugx != payment.amount_ugx:
            audit.record(db, action="payment.amount_mismatch", outcome="DENIED", target_type="payment",
                         target_id=str(payment.id), institution_id=institution_id,
                         details={"expected": payment.amount_ugx, "provider": status.amount_ugx, "source": source}, meta=meta)  # fmt: skip
            logger.error("payment_amount_mismatch", extra={"payment_id": str(payment.id)})
            return "MISMATCH"  # never mark paid on a wrong amount; staff must investigate
        if payment.status in (P.PAID, P.REFUNDED) or not can_pay_transition(payment.status, P.PAID):
            return "NOOP"
        if not _claim_target(db, payment, meta, institution_id):
            return "MISMATCH"
        payment.status = P.PAID
        payment.paid_at = _now()
        payment.failure_reason = None
        db.flush()
        _on_paid(db, payment, meta)
        audit.record(db, action="payment.paid", target_type="payment", target_id=str(payment.id),
                     institution_id=institution_id, details={"source": source, "amount_ugx": payment.amount_ugx}, meta=meta)  # fmt: skip
        return "PAID"
    if status.status == "FAILED" and payment.status == P.PENDING:
        _fail(db, payment, "provider_reported_failure")
        audit.record(db, action="payment.failed", target_type="payment", target_id=str(payment.id),
                     institution_id=institution_id, details={"source": source}, meta=meta)  # fmt: skip
        return "FAILED"
    return "NOOP"


# --------------------------------------------------------------------------- creating a payment


def _unavailable() -> ServiceUnavailableError:
    return ServiceUnavailableError(
        "Online payments are not available right now.", code="payments_unavailable"
    )


def create_online_payment(
    db: Session, principal: Principal, *, order_id: uuid.UUID | None, resource_id: uuid.UUID | None,
    idempotency_key: str | None, providers: dict[str, PaymentProvider], settings: Settings, meta: RequestMeta,
) -> Payment:  # fmt: skip
    if not settings.payments_available or settings.payment_provider not in providers:
        raise _unavailable()
    provider = providers[settings.payment_provider]
    user = principal.user
    fp = fingerprint({"order": order_id, "resource": resource_id})

    if idempotency_key:
        prior = db.scalar(
            select(Payment).where(
                Payment.payer_user_id == user.id, Payment.idempotency_key == idempotency_key
            )
        )
        if prior is not None:
            if prior.request_fingerprint != fp:
                raise ConflictError(
                    "That Idempotency-Key was already used for a different request.",
                    code="idempotency_key_reuse",
                )
            return prior

    order: PrintOrder | None = None
    if order_id is not None:
        order = db.scalar(
            select(PrintOrder)
            .where(PrintOrder.id == order_id, PrintOrder.student_id == user.id)
            .with_for_update()
        )
        if order is None:
            raise NotFoundError("Order not found.")
        principal.require("payment:create", order.institution_id)
        if order.payment_method != "ONLINE":
            raise ConflictError("This order is paid at pickup.", code="not_online_order")
        if order.status != OrderStatus.SUBMITTED:
            raise ConflictError("This order can't be paid for right now.", code="order_not_payable")
        if order.payment_status == P.PAID:
            raise ConflictError("This order is already paid.", code="already_paid")
        amount, target = order.total_ugx, {"purpose": "PRINT_ORDER", "print_order_id": order.id}
        active_filter = (Payment.print_order_id == order.id,)
        description = f"Print order {order.id}"
    else:
        resource = db.get(Resource, resource_id)
        if (
            resource is None
            or resource.status != ResourceStatus.PUBLISHED
            or resource.access_type != AccessType.PREMIUM
        ):
            raise NotFoundError("Resource not found.")
        if not principal.has_any_scope("payment:create"):
            raise ForbiddenError()
        if access.active_entitlement(db, user.id, resource.id) is not None:
            raise ConflictError(
                "You already have access to this resource.", code="already_entitled"
            )
        assert resource.price_ugx is not None
        amount, target = (
            resource.price_ugx,
            {"purpose": "RESOURCE_PURCHASE", "resource_id": resource.id},
        )
        active_filter = (Payment.payer_user_id == user.id, Payment.resource_id == resource.id)
        description = f"Premium resource {resource.id}"

    active = db.scalar(
        select(Payment)
        .where(*active_filter, Payment.status.in_((P.PENDING, P.PAID)))
        .with_for_update()
    )
    if active is not None:
        if active.status == P.PAID:
            raise ConflictError("This has already been paid for.", code="already_paid")
        if active.expires_at is not None and active.expires_at <= _now():
            _fail(
                db, active, "expired"
            )  # abandoned checkout: free the slot and start a new attempt
            db.flush()
        else:
            return active  # a checkout is already open: resume it instead of creating a second one

    payment = Payment(
        payer_user_id=user.id, amount_ugx=amount, method="ONLINE", provider=provider.name, status=P.PENDING,
        idempotency_key=idempotency_key, request_fingerprint=fp,
        expires_at=_now() + timedelta(minutes=settings.payment_pending_minutes), **target,
    )  # fmt: skip
    db.add(payment)
    try:
        db.flush()
    except IntegrityError:  # a concurrent request created the live payment first
        db.rollback()
        winner = db.scalar(select(Payment).where(*active_filter, Payment.status == P.PENDING))
        if winner is None:
            raise
        return winner
    if order is not None:
        _set_order_payment_status(order, P.PENDING)
    audit.record(db, action="payment.created", actor_user_id=user.id, target_type="payment", target_id=str(payment.id),
                 institution_id=payment_institution_id(db, payment), details={"amount_ugx": amount, "purpose": payment.purpose}, meta=meta)  # fmt: skip
    db.commit()  # the PENDING row is durable BEFORE we talk to the provider, so a crash never loses track of it

    try:
        result = provider.initiate(
            payment_id=str(payment.id), amount_ugx=amount, currency="UGX", description=description,
            return_url=f"{settings.public_app_url}/payments/{payment.id}", idempotency_key=str(payment.id),
        )  # fmt: skip
    except Exception as exc:
        db.rollback()
        refreshed = db.get(Payment, payment.id)
        assert refreshed is not None
        record_transaction(
            db,
            refreshed,
            "INITIATE",
            "FAILURE",
            amount=amount,
            detail={"error": type(exc).__name__},
        )
        _fail(db, refreshed, "provider_unavailable")
        db.commit()
        if isinstance(exc, ProviderError):
            raise ServiceUnavailableError(
                "The payment provider is unavailable. Please try again.",
                code="provider_unavailable",
            ) from exc
        raise
    payment.provider_reference = result.provider_reference
    payment.checkout_url = result.checkout_url
    record_transaction(
        db, payment, "INITIATE", "SUCCESS", reference=result.provider_reference, amount=amount
    )
    db.commit()
    return payment


# --------------------------------------------------------------------------- webhooks


@dataclass(frozen=True)
class WebhookResult:
    status: str  # PROCESSED | IGNORED | DUPLICATE


def process_webhook(
    db: Session, provider: PaymentProvider, headers: dict[str, str], body: bytes, meta: RequestMeta
) -> WebhookResult:
    try:
        event = provider.parse_webhook(headers, body)  # 1) signature (and timestamp) verified here
    except InvalidSignatureError as exc:
        logger.warning("webhook_rejected", extra={"provider": provider.name, "reason": str(exc)})
        raise UnauthorizedError("Invalid webhook signature.", code="invalid_signature") from exc

    # 2) de-duplicate. The unique index makes a concurrent duplicate wait for us, then do nothing.
    inserted = db.execute(
        pg_insert(PaymentEvent)
        .values(
            provider=provider.name, provider_event_id=event.event_id, event_type=event.event_type[:50],
            provider_reference=event.provider_reference[:100], payload=scrub(event.payload),
            processing_status="RECEIVED",
        )
        .on_conflict_do_nothing(constraint="uq_payment_events_provider_provider_event_id")
        .returning(PaymentEvent.id)
    ).scalar_one_or_none()  # fmt: skip
    if inserted is None:
        db.rollback()
        return WebhookResult("DUPLICATE")
    event_row = db.get(PaymentEvent, inserted)
    assert event_row is not None

    payment = db.scalar(
        select(Payment)
        .where(
            Payment.provider == provider.name,
            Payment.provider_reference == event.provider_reference,
        )
        .with_for_update()
    )
    if payment is None:
        event_row.processing_status, event_row.note, event_row.processed_at = (
            "IGNORED",
            "unknown_payment",
            _now(),
        )
        db.commit()
        return WebhookResult("IGNORED")
    event_row.payment_id = payment.id

    # 3) never trust the body: ask the provider. If it is unreachable we roll back EVERYTHING (including the
    #    event row) and return 503, so the provider retries later.
    try:
        status = provider.verify(payment.provider_reference or "")
    except ProviderError as exc:
        db.rollback()
        raise ServiceUnavailableError(
            "Could not verify the payment right now.", code="verification_unavailable"
        ) from exc
    record_transaction(
        db,
        payment,
        "VERIFY",
        "SUCCESS",
        reference=payment.provider_reference,
        amount=status.amount_ugx,
        detail={"status": status.status, "via": "webhook"},
    )

    # 4) one transaction: payment state + entitlement/order + event bookkeeping
    outcome = apply_provider_status(db, payment, status, source="webhook", meta=meta)
    event_row.processing_status = "PROCESSED" if outcome in ("PAID", "FAILED") else "IGNORED"
    event_row.note = outcome
    event_row.processed_at = _now()
    db.commit()
    return WebhookResult(event_row.processing_status)


def verify_payment(
    db: Session,
    principal: Principal,
    payment_id: uuid.UUID,
    providers: dict[str, PaymentProvider],
    meta: RequestMeta,
) -> Payment:
    """Owner-triggered re-check (for when a webhook is late). Same code path as the webhook."""
    payment = db.scalar(
        select(Payment)
        .where(Payment.id == payment_id, Payment.payer_user_id == principal.user.id)
        .with_for_update()
    )
    if payment is None:
        raise NotFoundError("Payment not found.")
    provider = providers.get(payment.provider)
    if payment.status in (P.PAID, P.REFUNDED) or provider is None or not payment.provider_reference:
        return payment
    try:
        status = provider.verify(payment.provider_reference)
    except ProviderError as exc:
        raise ServiceUnavailableError(
            "Could not check the payment right now.", code="verification_unavailable"
        ) from exc
    record_transaction(
        db,
        payment,
        "VERIFY",
        "SUCCESS",
        reference=payment.provider_reference,
        amount=status.amount_ugx,
        detail={"status": status.status, "via": "poll"},
    )
    apply_provider_status(db, payment, status, source="poll", meta=meta)
    db.commit()
    return payment


def get_payment(db: Session, principal: Principal, payment_id: uuid.UUID) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found.")
    if payment.payer_user_id != principal.user.id and not principal.can(
        "payment:read", payment_institution_id(db, payment)
    ):
        raise NotFoundError("Payment not found.")  # someone else's payment does not exist for you
    return payment


# --------------------------------------------------------------------------- refunds


def process_refund(
    db: Session,
    principal: Principal,
    payment_id: uuid.UUID,
    providers: dict[str, PaymentProvider],
    meta: RequestMeta,
) -> Refund:
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None or not principal.can("payment:manage", payment_institution_id(db, payment)):
        raise NotFoundError("Payment not found.")
    if payment.status != P.PAID:
        raise ConflictError("Only paid payments can be refunded.", code="not_refundable")
    if payment.provider == "CASH":
        raise ConflictError(
            "Cash payments are refunded by hand at the shop.", code="cash_refund_manual"
        )
    order: PrintOrder | None = None
    if payment.print_order_id is not None:
        order = db.scalar(
            select(PrintOrder).where(PrintOrder.id == payment.print_order_id).with_for_update()
        )
        assert order is not None
        if order.status not in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
            raise ConflictError(
                "Cancel or reject the order before refunding it.", code="order_still_active"
            )
    provider = providers.get(payment.provider)
    if provider is None:
        raise _unavailable()

    refund = request_refund(db, payment, "Refund processed by staff", principal.user.id)
    assert refund is not None
    if refund.status == "SUCCEEDED":
        raise ConflictError("This payment was already refunded.", code="already_refunded")
    try:
        result = provider.refund(provider_reference=payment.provider_reference or "", amount_ugx=refund.amount_ugx,
                                 reason=refund.reason, idempotency_key=str(refund.id))  # fmt: skip
    except ProviderError as exc:
        db.rollback()
        raise ServiceUnavailableError(
            "The payment provider is unavailable. Try again.", code="provider_unavailable"
        ) from exc
    refund.processed_by_user_id, refund.processed_at, refund.provider_reference = (
        principal.user.id,
        _now(),
        result.provider_reference,
    )
    record_transaction(db, payment, "REFUND", "SUCCESS" if result.status == "SUCCEEDED" else "FAILURE",
                       reference=result.provider_reference, amount=refund.amount_ugx)  # fmt: skip
    if result.status == "SUCCEEDED":
        refund.status = "SUCCEEDED"
        payment.status = P.REFUNDED
        if order is not None:
            _set_order_payment_status(order, P.REFUNDED)
        else:  # a refunded purchase no longer entitles the buyer
            entitlement = db.scalar(select(Entitlement).where(
                Entitlement.user_id == payment.payer_user_id, Entitlement.resource_id == payment.resource_id,
                Entitlement.source == "PURCHASE", Entitlement.source_reference == str(payment.id)))  # fmt: skip
            if entitlement is not None:
                entitlement.status, entitlement.revoked_at = "REVOKED", _now()
    else:
        refund.status = "FAILED"
    audit.record(db, action="refund.processed", outcome="SUCCESS" if refund.status == "SUCCEEDED" else "FAILURE",
                 actor_user_id=principal.user.id, target_type="payment", target_id=str(payment.id),
                 institution_id=payment_institution_id(db, payment), meta=meta)  # fmt: skip
    db.commit()
    return refund


# --------------------------------------------------------------------------- development simulator


def simulate_provider_event(
    db: Session, principal: Principal, payment_id: uuid.UUID, outcome: str,
    providers: dict[str, PaymentProvider], settings: Settings, meta: RequestMeta,
) -> WebhookResult:  # fmt: skip
    """Development only. Flips the FakeProvider's state, then delivers a correctly SIGNED webhook through the
    normal pipeline, so the same code that handles real providers is exercised."""
    provider = providers.get("fake")
    if settings.is_production or not isinstance(provider, FakeProvider):
        raise NotFoundError("Not found.")
    payment = db.get(Payment, payment_id)
    if (
        payment is None
        or payment.payer_user_id != principal.user.id
        or not payment.provider_reference
    ):
        raise NotFoundError("Payment not found.")
    provider.set_status(payment.provider_reference, "PAID" if outcome == "success" else "FAILED")
    event_type = "payment.succeeded" if outcome == "success" else "payment.failed"
    body, headers = provider.signed_webhook(
        f"evt_{uuid.uuid4().hex}", event_type, payment.provider_reference
    )
    return process_webhook(db, provider, headers, body, meta)
