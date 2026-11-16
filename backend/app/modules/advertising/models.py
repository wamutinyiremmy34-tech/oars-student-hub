"""Advertising models: campaigns, advertisements, targeting, and event tracking."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Valid advertisement statuses (lifecycle).
AD_STATUSES = ("DRAFT", "UNDER_REVIEW", "SCHEDULED", "ACTIVE", "PAUSED", "REJECTED", "ARCHIVED")
AD_STATUS_CHECK = f"status IN ({', '.join(repr(s) for s in AD_STATUSES)})"


class Advertiser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An organisation that places advertisements on the platform."""

    __tablename__ = "advertisers"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(254), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="advertiser")


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A group of advertisements with a shared budget/schedule concept."""

    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_advertiser_id", "advertiser_id"),
        Index("ix_campaigns_is_active", "is_active"),
    )

    advertiser_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advertisers.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    advertiser: Mapped["Advertiser"] = relationship(back_populates="campaigns")
    advertisements: Mapped[list["Advertisement"]] = relationship(back_populates="campaign")


class Advertisement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single advertisement creative with lifecycle state."""

    __tablename__ = "advertisements"
    __table_args__ = (
        CheckConstraint(AD_STATUS_CHECK, name="status_valid"),
        Index("ix_advertisements_campaign_id", "campaign_id"),
        Index("ix_advertisements_status", "status"),
        Index("ix_advertisements_starts_at", "starts_at"),
        Index("ix_advertisements_ends_at", "ends_at"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'DRAFT'")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Image URL or asset key.
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Destination URL when the user clicks the ad.
    click_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Placement slot (e.g. "dashboard_banner", "resource_sidebar").
    placement: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="'dashboard_banner'"
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped["Campaign"] = relationship(back_populates="advertisements")
    targets: Mapped[list["AdTarget"]] = relationship(
        back_populates="advertisement", cascade="all, delete-orphan"
    )
    events: Mapped[list["AdEvent"]] = relationship(back_populates="advertisement")


class AdTarget(UUIDPrimaryKeyMixin, Base):
    """Targeting constraint for an advertisement (institution scope)."""

    __tablename__ = "ad_targets"
    __table_args__ = (
        UniqueConstraint("advertisement_id", "institution_id", name="uq_ad_targets_ad_institution"),
        Index("ix_ad_targets_advertisement_id", "advertisement_id"),
        Index("ix_ad_targets_institution_id", "institution_id"),
    )

    advertisement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advertisements.id", ondelete="CASCADE"), nullable=False
    )
    # NULL = platform-wide (shown at all institutions).
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), nullable=True
    )

    advertisement: Mapped["Advertisement"] = relationship(back_populates="targets")


class AdEvent(UUIDPrimaryKeyMixin, Base):
    """Records an impression or click for basic analytics.

    We record the event type and a coarse timestamp; we do not record PII.
    Deduplication is approximate (no unique index) to avoid blocking browsing.
    """

    __tablename__ = "ad_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('IMPRESSION','CLICK')", name="event_type_valid"),
        Index("ix_ad_events_advertisement_id", "advertisement_id"),
        Index("ix_ad_events_event_type", "event_type"),
        Index("ix_ad_events_created_at", "created_at"),
    )

    advertisement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advertisements.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # Institution context (for aggregate analytics).
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    # We store no user ID — only an anonymous session token to cap duplicate counting.
    session_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    advertisement: Mapped["Advertisement"] = relationship(back_populates="events")
