"""Notifications (persistent in-app messages + outbox) and advertising
(advertisers, campaigns, advertisements, targets, ad_events).

Revision ID: 0004_notifications_advertising
Revises: 0003_printing_payments
Create Date: 2026-10-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_notifications_advertising"
down_revision: str | None = "0003_printing_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    # ─── notifications ────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        _id(),
        sa.Column(
            "recipient_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.Uuid(),
            sa.ForeignKey("institutions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(10), nullable=False, server_default="INFO"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("action_url", sa.String(500), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.CheckConstraint(
            "kind IN ('INFO','SUCCESS','WARNING','ERROR')", name="ck_notifications_kind_valid"
        ),
    )
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    # ─── notification_outbox ──────────────────────────────────────────────────
    op.create_table(
        "notification_outbox",
        _id(),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_notification_outbox"),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','PROCESSED','FAILED')",
            name="ck_notification_outbox_status_valid",
        ),
    )
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"])
    op.create_index("ix_notification_outbox_created_at", "notification_outbox", ["created_at"])

    # ─── advertisers ──────────────────────────────────────────────────────────
    op.create_table(
        "advertisers",
        _id(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_email", sa.String(254), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_advertisers"),
    )

    # ─── campaigns ────────────────────────────────────────────────────────────
    op.create_table(
        "campaigns",
        _id(),
        sa.Column(
            "advertiser_id",
            sa.Uuid(),
            sa.ForeignKey("advertisers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_campaigns"),
    )
    op.create_index("ix_campaigns_advertiser_id", "campaigns", ["advertiser_id"])
    op.create_index("ix_campaigns_is_active", "campaigns", ["is_active"])

    # ─── advertisements ───────────────────────────────────────────────────────
    _ad_statuses = (
        "'DRAFT', 'UNDER_REVIEW', 'SCHEDULED', 'ACTIVE', 'PAUSED', 'REJECTED', 'ARCHIVED'"
    )
    op.create_table(
        "advertisements",
        _id(),
        sa.Column(
            "campaign_id",
            sa.Uuid(),
            sa.ForeignKey("campaigns.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("click_url", sa.String(500), nullable=True),
        sa.Column("placement", sa.String(50), nullable=False, server_default="dashboard_banner"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_advertisements"),
        sa.CheckConstraint(f"status IN ({_ad_statuses})", name="ck_advertisements_status_valid"),
    )
    op.create_index("ix_advertisements_campaign_id", "advertisements", ["campaign_id"])
    op.create_index("ix_advertisements_status", "advertisements", ["status"])
    op.create_index("ix_advertisements_starts_at", "advertisements", ["starts_at"])
    op.create_index("ix_advertisements_ends_at", "advertisements", ["ends_at"])

    # ─── ad_targets ───────────────────────────────────────────────────────────
    op.create_table(
        "ad_targets",
        _id(),
        sa.Column(
            "advertisement_id",
            sa.Uuid(),
            sa.ForeignKey("advertisements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.Uuid(),
            sa.ForeignKey("institutions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ad_targets"),
        sa.UniqueConstraint(
            "advertisement_id", "institution_id", name="uq_ad_targets_ad_institution"
        ),
    )
    op.create_index("ix_ad_targets_advertisement_id", "ad_targets", ["advertisement_id"])
    op.create_index("ix_ad_targets_institution_id", "ad_targets", ["institution_id"])

    # ─── ad_events ────────────────────────────────────────────────────────────
    op.create_table(
        "ad_events",
        _id(),
        sa.Column(
            "advertisement_id",
            sa.Uuid(),
            sa.ForeignKey("advertisements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(10), nullable=False),
        sa.Column(
            "institution_id",
            sa.Uuid(),
            sa.ForeignKey("institutions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("session_token", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ad_events"),
        sa.CheckConstraint(
            "event_type IN ('IMPRESSION','CLICK')", name="ck_ad_events_event_type_valid"
        ),
    )
    op.create_index("ix_ad_events_advertisement_id", "ad_events", ["advertisement_id"])
    op.create_index("ix_ad_events_event_type", "ad_events", ["event_type"])
    op.create_index("ix_ad_events_created_at", "ad_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("ad_events")
    op.drop_table("ad_targets")
    op.drop_table("advertisements")
    op.drop_table("campaigns")
    op.drop_table("advertisers")
    op.drop_table("notification_outbox")
    op.drop_table("notifications")
