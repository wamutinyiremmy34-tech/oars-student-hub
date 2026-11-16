"""Print shops, pricing, documents and orders.

Database-level invariants (so no application bug can break them):
  * an order's shop must belong to the order's institution (composite FK);
  * a COMPLETED order must be PAID;
  * an ONLINE order cannot progress past SUBMITTED unless it is PAID.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.printing.state import OrderStatus, PaymentStatus


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PrintShop(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "print_shops"
    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_print_shops_institution_id_name"),
        UniqueConstraint("id", "institution_id", name="uq_print_shops_id_institution_id"),
        CheckConstraint(
            "max_outstanding_pickup_orders IS NULL OR max_outstanding_pickup_orders >= 0",
            name="max_outstanding_pickup_orders_non_negative",
        ),
    )

    # Several shops per institution are allowed (the unique key is per name, not per institution).
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    pay_on_pickup_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    max_outstanding_pickup_orders: Mapped[int | None] = mapped_column(Integer)


class PrintShopStaff(Base):
    """Which operators work at which shop. An operator sees only the orders of shops they belong to."""

    __tablename__ = "print_shop_staff"
    __table_args__ = (Index("ix_print_shop_staff_user_id", "user_id"),)

    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("print_shops.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PrintPricingRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One price. New option types need new rows, not new columns. Deactivate rather than delete:
    order snapshots refer to rule ids."""

    __tablename__ = "print_pricing_rules"
    __table_args__ = (
        CheckConstraint("kind IN ('PER_PAGE', 'PER_COPY', 'PER_ORDER')", name="kind_valid"),
        CheckConstraint(
            "color_mode IS NULL OR color_mode IN ('BW', 'COLOR')", name="color_mode_valid"
        ),
        CheckConstraint("amount_ugx >= 0", name="amount_non_negative"),
        CheckConstraint(
            "kind <> 'PER_PAGE' OR (paper_size IS NOT NULL AND color_mode IS NOT NULL "
            "AND option_key IS NULL AND amount_ugx > 0)",
            name="per_page_needs_dimensions",
        ),
        CheckConstraint(
            "kind = 'PER_PAGE' OR option_key IS NOT NULL", name="extras_need_option_key"
        ),
        Index("ix_print_pricing_rules_shop_id_is_active", "shop_id", "is_active"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("print_shops.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    paper_size: Mapped[str | None] = mapped_column(String(10))
    color_mode: Mapped[str | None] = mapped_column(String(5))
    duplex: Mapped[bool | None] = mapped_column(Boolean)
    option_key: Mapped[str | None] = mapped_column(String(30))
    amount_ugx: Mapped[int] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class PrintDocument(UUIDPrimaryKeyMixin, Base):
    """An uploaded document awaiting (or attached to) an order. The file itself is private storage."""

    __tablename__ = "print_documents"
    __table_args__ = (
        CheckConstraint("page_count >= 1", name="page_count_positive"),
        Index("ix_print_documents_student_id", "student_id"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), unique=True
    )
    page_count: Mapped[int] = mapped_column(
        Integer
    )  # counted by the SERVER, never taken from the client
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PrintOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "print_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "institution_id"], ["print_shops.id", "print_shops.institution_id"],
            name="fk_print_orders_shop_institution", ondelete="RESTRICT",
        ),
        UniqueConstraint("student_id", "idempotency_key", name="uq_print_orders_student_id_idempotency_key"),
        CheckConstraint(_in("status", OrderStatus.ALL), name="status_valid"),
        CheckConstraint(_in("payment_status", PaymentStatus.ALL), name="payment_status_valid"),
        CheckConstraint("payment_method IN ('ONLINE', 'PAY_ON_PICKUP')", name="payment_method_valid"),
        CheckConstraint("total_ugx > 0", name="total_positive"),
        CheckConstraint("status <> 'COMPLETED' OR payment_status = 'PAID'", name="completed_requires_payment"),
        CheckConstraint(
            "payment_method <> 'ONLINE' OR status IN ('DRAFT', 'SUBMITTED', 'CANCELLED', 'REJECTED') "
            "OR payment_status = 'PAID'",
            name="online_requires_payment_to_progress",
        ),
        Index("ix_print_orders_student_id_created_at", "student_id", "created_at"),
        Index("ix_print_orders_shop_id_status", "shop_id", "status"),
        Index("ix_print_orders_closed_at", "closed_at"),
    )  # fmt: skip

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    shop_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), server_default="SUBMITTED")
    payment_method: Mapped[str] = mapped_column(String(15))
    payment_status: Mapped[str] = mapped_column(String(10), server_default="UNPAID")
    total_ugx: Mapped[int] = mapped_column(BigInteger)  # integer UGX, calculated by the server
    price_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB
    )  # reproduces the price: rules, quantities, amounts
    note: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    reject_reason: Mapped[str | None] = mapped_column(String(500))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # entered a terminal state
    retention_hold: Mapped[bool] = mapped_column(Boolean, server_default="false")
    retention_hold_reason: Mapped[str | None] = mapped_column(String(255))


class PrintOrderItem(UUIDPrimaryKeyMixin, Base):
    """One document with its print options. Page count and prices are snapshots taken at ordering time."""

    __tablename__ = "print_order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "position", name="uq_print_order_items_order_id_position"),
        CheckConstraint("copies BETWEEN 1 AND 100", name="copies_range"),
        CheckConstraint("color_mode IN ('BW', 'COLOR')", name="color_mode_valid"),
        CheckConstraint("page_count >= 1", name="page_count_positive"),
        CheckConstraint("unit_price_ugx >= 0 AND line_total_ugx >= 0", name="prices_non_negative"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("print_orders.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("print_documents.id", ondelete="RESTRICT"), unique=True
    )
    copies: Mapped[int] = mapped_column(SmallInteger)
    paper_size: Mapped[str] = mapped_column(String(10))
    color_mode: Mapped[str] = mapped_column(String(5))
    duplex: Mapped[bool] = mapped_column(Boolean, server_default="false")
    options: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )  # future options
    page_count: Mapped[int] = mapped_column(Integer)
    unit_price_ugx: Mapped[int] = mapped_column(BigInteger)
    line_total_ugx: Mapped[int] = mapped_column(BigInteger)


class OrderStatusHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "order_status_history"
    __table_args__ = (
        CheckConstraint(_in("to_status", OrderStatus.ALL), name="to_status_valid"),
        CheckConstraint(
            f"from_status IS NULL OR {_in('from_status', OrderStatus.ALL)}",
            name="from_status_valid",
        ),
        Index("ix_order_status_history_order_id_created_at", "order_id", "created_at"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("print_orders.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(String(500))
    # The real moment of the event (clock_timestamp), not the start of the transaction (now()).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
