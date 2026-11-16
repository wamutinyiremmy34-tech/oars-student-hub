"""Print shops, pricing, orders, payments, provider transactions, webhook events and refunds.

Revision ID: 0003_printing_payments
Revises: 0002_academic_resources
Create Date: 2026-10-07
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_printing_payments"
down_revision: str | None = "0002_academic_resources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_PERMISSIONS = [
    ("payment:create", "Pay for orders and premium resources online", False),
    ("payment:record_cash", "Record cash received at pickup", False),
    ("printshop:manage", "Manage print shops, their staff and pricing", False),
    (
        "order:manage_any",
        "Act on any print order in the institution, and set retention holds",
        False,
    ),
]
# role -> new permissions it gains in this revision (ADMIN gets all four)
ROLE_GRANTS = {
    "STUDENT": ["payment:create"],
    "PRINTING_OPERATOR": ["payment:record_cash"],
    "ADMIN": ["payment:create", "payment:record_cash", "printshop:manage", "order:manage_any"],
}
ORDER_STATUSES = "'DRAFT', 'SUBMITTED', 'ACCEPTED', 'PRINTING', 'READY_FOR_PICKUP', 'COMPLETED', 'CANCELLED', 'REJECTED'"
PAYMENT_STATUSES = "'UNPAID', 'PENDING', 'PAID', 'FAILED', 'REFUNDED'"


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _ts_clock(name: str) -> sa.Column:
    """Event-log time: the real moment of the event (now() would be the start of the transaction)."""
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("clock_timestamp()"),
        nullable=False,
    )


def _tz(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _bool(name: str, default: bool) -> sa.Column:
    return sa.Column(
        name, sa.Boolean(), server_default=sa.true() if default else sa.false(), nullable=False
    )


def _fk(col: str, target: str, name: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([col], [target], name=op.f(name), ondelete=ondelete)


def upgrade() -> None:
    op.create_table(
        "print_shops",
        _id(), _uuid("institution_id"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        _bool("is_active", True), _bool("pay_on_pickup_enabled", True),
        sa.Column("max_outstanding_pickup_orders", sa.Integer(), nullable=True),
        _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_shops")),
        _fk("institution_id", "institutions.id", "fk_print_shops_institution_id_institutions", "RESTRICT"),
        sa.UniqueConstraint("institution_id", "name", name="uq_print_shops_institution_id_name"),
        sa.UniqueConstraint("id", "institution_id", name="uq_print_shops_id_institution_id"),
        sa.CheckConstraint(
            "max_outstanding_pickup_orders IS NULL OR max_outstanding_pickup_orders >= 0",
            name=op.f("ck_print_shops_max_outstanding_pickup_orders_non_negative"),
        ),
    )  # fmt: skip

    op.create_table(
        "print_shop_staff",
        _uuid("shop_id"), _uuid("user_id"), _uuid("added_by_user_id", nullable=True), _ts("created_at"),
        sa.PrimaryKeyConstraint("shop_id", "user_id", name=op.f("pk_print_shop_staff")),
        _fk("shop_id", "print_shops.id", "fk_print_shop_staff_shop_id_print_shops", "CASCADE"),
        _fk("user_id", "users.id", "fk_print_shop_staff_user_id_users", "CASCADE"),
        _fk("added_by_user_id", "users.id", "fk_print_shop_staff_added_by_user_id_users", "SET NULL"),
    )  # fmt: skip
    op.create_index("ix_print_shop_staff_user_id", "print_shop_staff", ["user_id"])

    op.create_table(
        "print_pricing_rules",
        _id(), _uuid("shop_id"),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("paper_size", sa.String(10), nullable=True),
        sa.Column("color_mode", sa.String(5), nullable=True),
        sa.Column("duplex", sa.Boolean(), nullable=True),
        sa.Column("option_key", sa.String(30), nullable=True),
        sa.Column("amount_ugx", sa.BigInteger(), nullable=False),
        _bool("is_active", True), _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_pricing_rules")),
        _fk("shop_id", "print_shops.id", "fk_print_pricing_rules_shop_id_print_shops", "CASCADE"),
        sa.CheckConstraint("kind IN ('PER_PAGE', 'PER_COPY', 'PER_ORDER')", name=op.f("ck_print_pricing_rules_kind_valid")),
        sa.CheckConstraint("color_mode IS NULL OR color_mode IN ('BW', 'COLOR')", name=op.f("ck_print_pricing_rules_color_mode_valid")),
        sa.CheckConstraint("amount_ugx >= 0", name=op.f("ck_print_pricing_rules_amount_non_negative")),
        sa.CheckConstraint(
            "kind <> 'PER_PAGE' OR (paper_size IS NOT NULL AND color_mode IS NOT NULL "
            "AND option_key IS NULL AND amount_ugx > 0)",
            name=op.f("ck_print_pricing_rules_per_page_needs_dimensions"),
        ),
        sa.CheckConstraint("kind = 'PER_PAGE' OR option_key IS NOT NULL", name=op.f("ck_print_pricing_rules_extras_need_option_key")),
    )  # fmt: skip
    op.create_index(
        "ix_print_pricing_rules_shop_id_is_active", "print_pricing_rules", ["shop_id", "is_active"]
    )

    op.create_table(
        "print_documents",
        _id(), _uuid("student_id"), _uuid("file_id"),
        sa.Column("page_count", sa.Integer(), nullable=False),
        _tz("purged_at"), _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_documents")),
        _fk("student_id", "users.id", "fk_print_documents_student_id_users", "RESTRICT"),
        _fk("file_id", "stored_files.id", "fk_print_documents_file_id_stored_files", "RESTRICT"),
        sa.UniqueConstraint("file_id", name=op.f("uq_print_documents_file_id")),
        sa.CheckConstraint("page_count >= 1", name=op.f("ck_print_documents_page_count_positive")),
    )  # fmt: skip
    op.create_index("ix_print_documents_student_id", "print_documents", ["student_id"])

    op.create_table(
        "print_orders",
        _id(), _uuid("student_id"), _uuid("shop_id"), _uuid("institution_id"),
        sa.Column("status", sa.String(20), server_default="SUBMITTED", nullable=False),
        sa.Column("payment_method", sa.String(15), nullable=False),
        sa.Column("payment_status", sa.String(10), server_default="UNPAID", nullable=False),
        sa.Column("total_ugx", sa.BigInteger(), nullable=False),
        sa.Column("price_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("reject_reason", sa.String(500), nullable=True),
        _tz("submitted_at"), _tz("closed_at"),
        _bool("retention_hold", False),
        sa.Column("retention_hold_reason", sa.String(255), nullable=True),
        _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_orders")),
        _fk("student_id", "users.id", "fk_print_orders_student_id_users", "RESTRICT"),
        sa.ForeignKeyConstraint(["shop_id", "institution_id"], ["print_shops.id", "print_shops.institution_id"], name="fk_print_orders_shop_institution", ondelete="RESTRICT"),
        sa.UniqueConstraint("student_id", "idempotency_key", name="uq_print_orders_student_id_idempotency_key"),
        sa.CheckConstraint(f"status IN ({ORDER_STATUSES})", name=op.f("ck_print_orders_status_valid")),
        sa.CheckConstraint(f"payment_status IN ({PAYMENT_STATUSES})", name=op.f("ck_print_orders_payment_status_valid")),
        sa.CheckConstraint("payment_method IN ('ONLINE', 'PAY_ON_PICKUP')", name=op.f("ck_print_orders_payment_method_valid")),
        sa.CheckConstraint("total_ugx > 0", name=op.f("ck_print_orders_total_positive")),
        sa.CheckConstraint("status <> 'COMPLETED' OR payment_status = 'PAID'", name=op.f("ck_print_orders_completed_requires_payment")),
        sa.CheckConstraint(
            "payment_method <> 'ONLINE' OR status IN ('DRAFT', 'SUBMITTED', 'CANCELLED', 'REJECTED') "
            "OR payment_status = 'PAID'",
            name=op.f("ck_print_orders_online_requires_payment_to_progress"),
        ),
    )  # fmt: skip
    op.create_index(
        "ix_print_orders_student_id_created_at", "print_orders", ["student_id", "created_at"]
    )
    op.create_index("ix_print_orders_shop_id_status", "print_orders", ["shop_id", "status"])
    op.create_index("ix_print_orders_closed_at", "print_orders", ["closed_at"])

    op.create_table(
        "print_order_items",
        _id(), _uuid("order_id"),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        _uuid("document_id"),
        sa.Column("copies", sa.SmallInteger(), nullable=False),
        sa.Column("paper_size", sa.String(10), nullable=False),
        sa.Column("color_mode", sa.String(5), nullable=False),
        _bool("duplex", False),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("unit_price_ugx", sa.BigInteger(), nullable=False),
        sa.Column("line_total_ugx", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_order_items")),
        _fk("order_id", "print_orders.id", "fk_print_order_items_order_id_print_orders", "CASCADE"),
        _fk("document_id", "print_documents.id", "fk_print_order_items_document_id_print_documents", "RESTRICT"),
        sa.UniqueConstraint("order_id", "position", name="uq_print_order_items_order_id_position"),
        sa.UniqueConstraint("document_id", name=op.f("uq_print_order_items_document_id")),
        sa.CheckConstraint("copies BETWEEN 1 AND 100", name=op.f("ck_print_order_items_copies_range")),
        sa.CheckConstraint("color_mode IN ('BW', 'COLOR')", name=op.f("ck_print_order_items_color_mode_valid")),
        sa.CheckConstraint("page_count >= 1", name=op.f("ck_print_order_items_page_count_positive")),
        sa.CheckConstraint("unit_price_ugx >= 0 AND line_total_ugx >= 0", name=op.f("ck_print_order_items_prices_non_negative")),
    )  # fmt: skip

    op.create_table(
        "order_status_history",
        _id(), _uuid("order_id"),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        _uuid("actor_user_id", nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        _ts_clock("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_status_history")),
        _fk("order_id", "print_orders.id", "fk_order_status_history_order_id_print_orders", "CASCADE"),
        _fk("actor_user_id", "users.id", "fk_order_status_history_actor_user_id_users", "SET NULL"),
        sa.CheckConstraint(f"to_status IN ({ORDER_STATUSES})", name=op.f("ck_order_status_history_to_status_valid")),
        sa.CheckConstraint(f"from_status IS NULL OR from_status IN ({ORDER_STATUSES})", name=op.f("ck_order_status_history_from_status_valid")),
    )  # fmt: skip
    op.create_index(
        "ix_order_status_history_order_id_created_at",
        "order_status_history",
        ["order_id", "created_at"],
    )

    op.create_table(
        "payments",
        _id(), _uuid("payer_user_id"),
        sa.Column("purpose", sa.String(20), nullable=False),
        _uuid("print_order_id", nullable=True), _uuid("resource_id", nullable=True),
        sa.Column("amount_ugx", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), server_default="UGX", nullable=False),
        sa.Column("method", sa.String(15), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        sa.Column("checkout_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(10), server_default="PENDING", nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=True),
        sa.Column("failure_reason", sa.String(255), nullable=True),
        _uuid("recorded_by_user_id", nullable=True),
        _tz("expires_at"), _tz("paid_at"), _tz("failed_at"),
        _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        _fk("payer_user_id", "users.id", "fk_payments_payer_user_id_users", "RESTRICT"),
        _fk("print_order_id", "print_orders.id", "fk_payments_print_order_id_print_orders", "RESTRICT"),
        _fk("resource_id", "resources.id", "fk_payments_resource_id_resources", "RESTRICT"),
        _fk("recorded_by_user_id", "users.id", "fk_payments_recorded_by_user_id_users", "SET NULL"),
        sa.UniqueConstraint("provider", "provider_reference", name="uq_payments_provider_provider_reference"),
        sa.UniqueConstraint("payer_user_id", "idempotency_key", name="uq_payments_payer_user_id_idempotency_key"),
        sa.CheckConstraint("purpose IN ('PRINT_ORDER', 'RESOURCE_PURCHASE')", name=op.f("ck_payments_purpose_valid")),
        sa.CheckConstraint(
            "(purpose = 'PRINT_ORDER' AND print_order_id IS NOT NULL AND resource_id IS NULL) OR "
            "(purpose = 'RESOURCE_PURCHASE' AND resource_id IS NOT NULL AND print_order_id IS NULL)",
            name=op.f("ck_payments_target_matches_purpose"),
        ),
        sa.CheckConstraint("amount_ugx > 0", name=op.f("ck_payments_amount_positive")),
        sa.CheckConstraint("currency = 'UGX'", name=op.f("ck_payments_currency_ugx")),
        sa.CheckConstraint("method IN ('ONLINE', 'PAY_ON_PICKUP')", name=op.f("ck_payments_method_valid")),
        sa.CheckConstraint("status IN ('PENDING', 'PAID', 'FAILED', 'REFUNDED')", name=op.f("ck_payments_status_valid")),
        sa.CheckConstraint(
            "(method = 'ONLINE' AND provider <> 'CASH') OR (method = 'PAY_ON_PICKUP' AND provider = 'CASH')",
            name=op.f("ck_payments_provider_matches_method"),
        ),
        sa.CheckConstraint("provider <> 'CASH' OR status IN ('PAID', 'REFUNDED')", name=op.f("ck_payments_cash_is_paid")),
    )  # fmt: skip
    op.create_index(
        "uq_payments_active_print_order", "payments", ["print_order_id"], unique=True,
        postgresql_where=sa.text("print_order_id IS NOT NULL AND status IN ('PENDING', 'PAID')"),
    )  # fmt: skip
    op.create_index(
        "uq_payments_active_resource", "payments", ["payer_user_id", "resource_id"], unique=True,
        postgresql_where=sa.text("resource_id IS NOT NULL AND status IN ('PENDING', 'PAID')"),
    )  # fmt: skip
    op.create_index("ix_payments_payer_user_id", "payments", ["payer_user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "payment_transactions",
        _id(), _uuid("payment_id"),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        sa.Column("amount_ugx", sa.BigInteger(), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        _ts_clock("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_transactions")),
        _fk("payment_id", "payments.id", "fk_payment_transactions_payment_id_payments", "RESTRICT"),
        sa.CheckConstraint("kind IN ('INITIATE', 'VERIFY', 'REFUND')", name=op.f("ck_payment_transactions_kind_valid")),
        sa.CheckConstraint("outcome IN ('SUCCESS', 'FAILURE')", name=op.f("ck_payment_transactions_outcome_valid")),
    )  # fmt: skip
    op.create_index("ix_payment_transactions_payment_id", "payment_transactions", ["payment_id"])

    op.create_table(
        "payment_events",
        _id(),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        _uuid("payment_id", nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processing_status", sa.String(10), server_default="RECEIVED", nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        _ts_clock("received_at"), _tz("processed_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
        _fk("payment_id", "payments.id", "fk_payment_events_payment_id_payments", "SET NULL"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_payment_events_provider_provider_event_id"),
        sa.CheckConstraint("processing_status IN ('RECEIVED', 'PROCESSED', 'IGNORED', 'FAILED')", name=op.f("ck_payment_events_processing_status_valid")),
    )  # fmt: skip
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"])

    op.create_table(
        "refunds",
        _id(), _uuid("payment_id"),
        sa.Column("amount_ugx", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("status", sa.String(10), server_default="REQUESTED", nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        _uuid("requested_by_user_id", nullable=True), _uuid("processed_by_user_id", nullable=True),
        _tz("processed_at"), _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refunds")),
        _fk("payment_id", "payments.id", "fk_refunds_payment_id_payments", "RESTRICT"),
        _fk("requested_by_user_id", "users.id", "fk_refunds_requested_by_user_id_users", "SET NULL"),
        _fk("processed_by_user_id", "users.id", "fk_refunds_processed_by_user_id_users", "SET NULL"),
        sa.CheckConstraint("amount_ugx > 0", name=op.f("ck_refunds_amount_positive")),
        sa.CheckConstraint("status IN ('REQUESTED', 'SUCCEEDED', 'FAILED')", name=op.f("ck_refunds_status_valid")),
    )  # fmt: skip
    op.create_index(
        "uq_refunds_open_payment", "refunds", ["payment_id"], unique=True,
        postgresql_where=sa.text("status IN ('REQUESTED', 'SUCCEEDED')"),
    )  # fmt: skip
    op.create_index("ix_refunds_status", "refunds", ["status"])

    _seed_permissions()


def _seed_permissions() -> None:
    permissions = sa.table(
        "permissions", sa.column("id", sa.Uuid()), sa.column("code", sa.String()),
        sa.column("description", sa.String()), sa.column("platform_only", sa.Boolean()),
    )  # fmt: skip
    ids = {code: uuid.uuid4() for code, _, _ in NEW_PERMISSIONS}
    op.bulk_insert(
        permissions,
        [
            {"id": ids[c], "code": c, "description": d, "platform_only": po}
            for c, d, po in NEW_PERMISSIONS
        ],
    )
    bind = op.get_bind()
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid()), sa.column("permission_id", sa.Uuid())
    )
    rows = []
    for role, codes in ROLE_GRANTS.items():
        role_id = bind.execute(
            sa.text("SELECT id FROM roles WHERE name = :n"), {"n": role}
        ).scalar_one()
        rows += [{"role_id": role_id, "permission_id": ids[c]} for c in codes]
    op.bulk_insert(role_permissions, rows)


def downgrade() -> None:
    codes = ", ".join(f"'{c}'" for c, _, _ in NEW_PERMISSIONS)
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes})")  # role_permissions rows cascade
    for table in (
        "refunds", "payment_events", "payment_transactions", "payments", "order_status_history",
        "print_order_items", "print_orders", "print_documents", "print_pricing_rules",
        "print_shop_staff", "print_shops",
    ):  # fmt: skip
        op.drop_table(table)
