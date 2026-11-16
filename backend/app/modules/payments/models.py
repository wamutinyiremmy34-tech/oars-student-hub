"""Payments. A payment is separate from the thing it pays for: one table serves print orders now and
premium resources too. Provider interactions and webhook events are logged separately."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_reference", name="uq_payments_provider_provider_reference"),
        UniqueConstraint("payer_user_id", "idempotency_key", name="uq_payments_payer_user_id_idempotency_key"),
        CheckConstraint("purpose IN ('PRINT_ORDER', 'RESOURCE_PURCHASE')", name="purpose_valid"),
        CheckConstraint(
            "(purpose = 'PRINT_ORDER' AND print_order_id IS NOT NULL AND resource_id IS NULL) OR "
            "(purpose = 'RESOURCE_PURCHASE' AND resource_id IS NOT NULL AND print_order_id IS NULL)",
            name="target_matches_purpose",
        ),
        CheckConstraint("amount_ugx > 0", name="amount_positive"),
        CheckConstraint("currency = 'UGX'", name="currency_ugx"),
        CheckConstraint("method IN ('ONLINE', 'PAY_ON_PICKUP')", name="method_valid"),
        CheckConstraint("status IN ('PENDING', 'PAID', 'FAILED', 'REFUNDED')", name="status_valid"),
        CheckConstraint(
            "(method = 'ONLINE' AND provider <> 'CASH') OR (method = 'PAY_ON_PICKUP' AND provider = 'CASH')",
            name="provider_matches_method",
        ),
        # Cash is only ever recorded after it was received, so it can never be pending or failed.
        CheckConstraint("provider <> 'CASH' OR status IN ('PAID', 'REFUNDED')", name="cash_is_paid"),
        # At most one live (pending or paid) payment per order and per user+resource.
        Index(
            "uq_payments_active_print_order", "print_order_id", unique=True,
            postgresql_where=text("print_order_id IS NOT NULL AND status IN ('PENDING', 'PAID')"),
        ),
        Index(
            "uq_payments_active_resource", "payer_user_id", "resource_id", unique=True,
            postgresql_where=text("resource_id IS NOT NULL AND status IN ('PENDING', 'PAID')"),
        ),
        Index("ix_payments_payer_user_id", "payer_user_id"),
        Index("ix_payments_status", "status"),
    )  # fmt: skip

    payer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    purpose: Mapped[str] = mapped_column(String(20))
    print_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("print_orders.id", ondelete="RESTRICT")
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resources.id", ondelete="RESTRICT")
    )
    amount_ugx: Mapped[int] = mapped_column(
        BigInteger
    )  # integer UGX; set by the server, never by the client
    currency: Mapped[str] = mapped_column(String(3), server_default="UGX")
    method: Mapped[str] = mapped_column(String(15))
    provider: Mapped[str] = mapped_column(String(20))  # 'fake', a future real provider, or 'CASH'
    provider_reference: Mapped[str | None] = mapped_column(String(100))
    checkout_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10), server_default="PENDING")
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentTransaction(UUIDPrimaryKeyMixin, Base):
    """Every call to a provider (initiate / verify / refund) and its outcome. Contains no secrets."""

    __tablename__ = "payment_transactions"
    __table_args__ = (
        CheckConstraint("kind IN ('INITIATE', 'VERIFY', 'REFUND')", name="kind_valid"),
        CheckConstraint("outcome IN ('SUCCESS', 'FAILURE')", name="outcome_valid"),
        Index("ix_payment_transactions_payment_id", "payment_id"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(10))
    outcome: Mapped[str] = mapped_column(String(10))
    provider_reference: Mapped[str | None] = mapped_column(String(100))
    amount_ugx: Mapped[int | None] = mapped_column(BigInteger)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class PaymentEvent(UUIDPrimaryKeyMixin, Base):
    """Every provider webhook that passed signature verification. (provider, provider_event_id) is UNIQUE,
    which is what makes duplicate and replayed deliveries harmless."""

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_event_id", name="uq_payment_events_provider_provider_event_id"
        ),
        CheckConstraint(
            "processing_status IN ('RECEIVED', 'PROCESSED', 'IGNORED', 'FAILED')",
            name="processing_status_valid",
        ),
        Index("ix_payment_events_payment_id", "payment_id"),
    )

    provider: Mapped[str] = mapped_column(String(20))
    provider_event_id: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(50))
    provider_reference: Mapped[str | None] = mapped_column(String(100))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)  # scrubbed of anything secret-looking
    processing_status: Mapped[str] = mapped_column(String(10), server_default="RECEIVED")
    note: Mapped[str | None] = mapped_column(String(255))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Refund(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount_ugx > 0", name="amount_positive"),
        CheckConstraint("status IN ('REQUESTED', 'SUCCEEDED', 'FAILED')", name="status_valid"),
        # One open-or-completed refund per payment: a payment cannot be refunded twice.
        Index(
            "uq_refunds_open_payment", "payment_id", unique=True,
            postgresql_where=text("status IN ('REQUESTED', 'SUCCEEDED')"),
        ),
        Index("ix_refunds_status", "status"),
    )  # fmt: skip

    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"))
    amount_ugx: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(10), server_default="REQUESTED")
    provider_reference: Mapped[str | None] = mapped_column(String(100))
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    processed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
