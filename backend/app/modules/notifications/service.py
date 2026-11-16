"""Notification service: create, list, mark as read, and outbox processing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.notifications.models import Notification, NotificationOutbox

_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


# ─────────────────────────────────────────────────────────────────────────────
# Creation helpers
# ─────────────────────────────────────────────────────────────────────────────


def create_notification(
    db: Session,
    *,
    recipient_id: uuid.UUID,
    title: str,
    body: str | None = None,
    kind: str = "INFO",
    action_url: str | None = None,
    institution_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> Notification:
    """Create and add a notification in the current session.  Caller is responsible for committing."""
    n = Notification(
        recipient_id=recipient_id,
        institution_id=institution_id,
        kind=kind,
        title=title,
        body=body,
        action_url=action_url,
        meta=meta,
    )
    db.add(n)
    db.flush()
    return n


def enqueue_notification_event(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> NotificationOutbox | None:
    """Add an outbox entry for *event_type* if one does not already exist (idempotent).

    Returns the entry, or None if it was already present.
    """
    existing = db.scalar(
        select(NotificationOutbox).where(
            NotificationOutbox.event_type == event_type,
            NotificationOutbox.entity_type == entity_type,
            NotificationOutbox.entity_id == entity_id,
        )
    )
    if existing is not None:
        return None
    entry = NotificationOutbox(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        status="PENDING",
        attempts=0,
    )
    db.add(entry)
    db.flush()
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# Read operations
# ─────────────────────────────────────────────────────────────────────────────


def list_notifications(
    db: Session,
    *,
    recipient_id: uuid.UUID,
    unread_only: bool = False,
    page: int = 1,
    page_size: int = _PAGE_SIZE,
) -> tuple[list[Notification], int]:
    """Return (items, total) for the recipient's notifications, newest first."""
    page_size = min(max(1, page_size), _MAX_PAGE_SIZE)
    offset = (max(1, page) - 1) * page_size

    q = select(Notification).where(Notification.recipient_id == recipient_id)
    if unread_only:
        q = q.where(Notification.is_read.is_(False))

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0

    items = list(
        db.scalars(q.order_by(Notification.created_at.desc()).offset(offset).limit(page_size))
    )
    return items, total


def get_unread_count(db: Session, *, recipient_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count()).where(
                Notification.recipient_id == recipient_id,
                Notification.is_read.is_(False),
            )
        )
        or 0
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mark as read
# ─────────────────────────────────────────────────────────────────────────────


def mark_read(
    db: Session,
    *,
    recipient_id: uuid.UUID,
    ids: list[uuid.UUID] | None = None,
) -> int:
    """Mark notifications as read.  If *ids* is empty/None, marks ALL unread for the recipient.

    Returns the count updated.  Silently ignores IDs that belong to other users.
    """
    now = datetime.now(UTC)
    q = (
        update(Notification)
        .where(
            Notification.recipient_id == recipient_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=now)
    )
    if ids:
        q = q.where(Notification.id.in_(ids))
    result = db.execute(q)
    db.commit()
    return result.rowcount  # type: ignore[return-value]


# ─────────────────────────────────────────────────────────────────────────────
# Outbox processing helpers (called from within a request or a background task)
# ─────────────────────────────────────────────────────────────────────────────

# Maximum retry attempts before an entry is marked FAILED permanently.
_MAX_ATTEMPTS = 5


def process_pending_outbox(db: Session, *, limit: int = 50) -> int:
    """Process up to *limit* PENDING outbox entries synchronously.

    For each entry we call _dispatch(), which creates the corresponding Notification rows.
    This is run opportunistically inside request lifecycles; a real deployment would run
    it as a periodic background job.

    Returns the number of entries processed.
    """
    entries = list(
        db.scalars(
            select(NotificationOutbox)
            .where(NotificationOutbox.status.in_(["PENDING"]))
            .order_by(NotificationOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    processed = 0
    for entry in entries:
        entry.status = "PROCESSING"
        entry.attempts = (entry.attempts or 0) + 1
        db.flush()
        try:
            _dispatch(db, entry)
            entry.status = "PROCESSED"
            entry.processed_at = datetime.now(UTC)
        except Exception as exc:  # noqa: BLE001
            entry.last_error = str(exc)[:500]
            entry.status = "FAILED" if entry.attempts >= _MAX_ATTEMPTS else "PENDING"
        db.flush()
        processed += 1
    db.commit()
    return processed


def _dispatch(db: Session, entry: NotificationOutbox) -> None:
    """Convert an outbox entry into Notification rows.  Must be idempotent at the row level."""
    payload = entry.payload
    event = entry.event_type

    # Resource moderation events
    if event == "resource.submitted":
        _notify_reviewers(db, payload)
    elif event == "resource.approved":
        _notify_one(db, payload, "Resource approved", kind="SUCCESS")
    elif event == "resource.rejected":
        _notify_one(db, payload, "Resource rejected", kind="ERROR")
    elif event == "resource.published":
        _notify_one(db, payload, "Resource published", kind="SUCCESS")

    # Printing order events
    elif event in (
        "order.accepted",
        "order.ready",
        "order.completed",
        "order.rejected",
        "order.cancelled",
    ):
        _notify_one(db, payload, _order_title(event), kind=_order_kind(event))

    # Payment events
    elif event == "payment.confirmed":
        _notify_one(db, payload, "Payment confirmed", kind="SUCCESS")
    elif event == "payment.failed":
        _notify_one(db, payload, "Payment failed", kind="ERROR")

    # Ignore unknown events (future extensibility)


def _notify_one(db: Session, payload: dict[str, Any], title: str, *, kind: str = "INFO") -> None:
    recipient_id = uuid.UUID(payload["recipient_id"])
    create_notification(
        db,
        recipient_id=recipient_id,
        title=title,
        body=payload.get("body"),
        kind=kind,
        action_url=payload.get("action_url"),
        institution_id=uuid.UUID(payload["institution_id"])
        if payload.get("institution_id")
        else None,
        meta={"event_type": payload.get("event_type"), "entity_id": payload.get("entity_id")},
    )


def _notify_reviewers(db: Session, payload: dict[str, Any]) -> None:
    """Create a notification for each reviewer listed in the payload."""
    reviewer_ids: list[str] = payload.get("reviewer_ids", [])
    for rid in reviewer_ids:
        create_notification(
            db,
            recipient_id=uuid.UUID(rid),
            title="New resource submitted for review",
            body=payload.get("body"),
            kind="INFO",
            action_url=payload.get("action_url"),
            institution_id=uuid.UUID(payload["institution_id"])
            if payload.get("institution_id")
            else None,
        )


def _order_title(event: str) -> str:
    return {
        "order.accepted": "Print order accepted",
        "order.ready": "Print order ready for pickup",
        "order.completed": "Print order completed",
        "order.rejected": "Print order rejected",
        "order.cancelled": "Print order cancelled",
    }.get(event, "Print order update")


def _order_kind(event: str) -> str:
    if event in ("order.completed", "order.accepted", "order.ready"):
        return "SUCCESS"
    if event in ("order.rejected", "order.cancelled"):
        return "WARNING"
    return "INFO"
