"""Notification models: in-app messages and a transactional outbox for reliable delivery."""

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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A persistent in-app notification for a single recipient.

    Notifications are append-only at the application layer: they are never edited,
    only marked as read.  Deletion is reserved for future retention policies.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('INFO','SUCCESS','WARNING','ERROR')",
            name="kind_valid",
        ),
        Index("ix_notifications_recipient_id", "recipient_id"),
        Index("ix_notifications_is_read", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
    )

    # RESTRICT: users are suspended, never deleted.
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Optional institution context (used for scoped admin queries).
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False, server_default="INFO")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional deep-link into the app (e.g. "/print/orders/<id>").
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Structured payload for rich notifications (not exposed to recipients).
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class NotificationOutbox(UUIDPrimaryKeyMixin, Base):
    """Transactional outbox entry.  Created in the same transaction as the business event it records.

    A background job (or a simple endpoint called from within a request lifecycle) processes pending
    entries and marks them PROCESSED or FAILED.  Idempotent: the (event_type, entity_id) pair is
    unique, so retrying a failed delivery cannot create duplicates.
    """

    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','PROCESSING','PROCESSED','FAILED')",
            name="status_valid",
        ),
        Index("ix_notification_outbox_status", "status"),
        Index("ix_notification_outbox_created_at", "created_at"),
    )

    # Idempotency key: same event cannot produce two outbox entries.
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, server_default="'PENDING'")
    attempts: Mapped[int] = mapped_column(nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
