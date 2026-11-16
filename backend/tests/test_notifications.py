"""Notification tests: recipient ownership, read/unread, outbox processing, idempotency.

These are integration tests: they require a running PostgreSQL (docker compose up -d).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from helpers import auth_headers, make_institution, make_user
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.notifications import service as notif_service
from app.modules.notifications.models import Notification, NotificationOutbox

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- recipient ownership


def test_list_notifications_returns_only_the_recipients_own(
    api_client: TestClient, db: Session
) -> None:
    institution = make_institution(db)
    alice = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])
    bob = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    notif_service.create_notification(
        db, recipient_id=alice.id, title="Alice's notification", kind="INFO"
    )
    notif_service.create_notification(
        db, recipient_id=bob.id, title="Bob's notification", kind="INFO"
    )
    db.commit()

    response = api_client.get("/api/v1/notifications", headers=auth_headers(alice))
    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["title"] == "Alice's notification"


def test_unread_count_is_per_recipient(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    alice = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])
    bob = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    notif_service.create_notification(db, recipient_id=alice.id, title="N1", kind="INFO")
    notif_service.create_notification(db, recipient_id=alice.id, title="N2", kind="INFO")
    notif_service.create_notification(db, recipient_id=bob.id, title="N3", kind="INFO")
    db.commit()

    assert (
        api_client.get("/api/v1/notifications/unread-count", headers=auth_headers(alice)).json()[
            "data"
        ]["count"]
        == 2
    )
    assert (
        api_client.get("/api/v1/notifications/unread-count", headers=auth_headers(bob)).json()[
            "data"
        ]["count"]
        == 1
    )


def test_unauthenticated_request_is_rejected(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/notifications").status_code == 401
    assert api_client.get("/api/v1/notifications/unread-count").status_code == 401


# --------------------------------------------------------------------------- read / unread


def test_mark_specific_ids_as_read(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    user = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    n1 = notif_service.create_notification(db, recipient_id=user.id, title="N1", kind="INFO")
    n2 = notif_service.create_notification(db, recipient_id=user.id, title="N2", kind="INFO")
    notif_service.create_notification(db, recipient_id=user.id, title="N3", kind="INFO")
    db.commit()

    response = api_client.post(
        "/api/v1/notifications/mark-read",
        json={"ids": [str(n1.id), str(n2.id)]},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    assert response.json()["data"]["message"].startswith("2")

    # Only n3 should still be unread.
    assert (
        api_client.get("/api/v1/notifications/unread-count", headers=auth_headers(user)).json()[
            "data"
        ]["count"]
        == 1
    )


def test_mark_all_as_read_with_empty_ids(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    user = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    for i in range(3):
        notif_service.create_notification(db, recipient_id=user.id, title=f"N{i}", kind="INFO")
    db.commit()

    response = api_client.post(
        "/api/v1/notifications/mark-read",
        json={"ids": []},
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    assert (
        api_client.get("/api/v1/notifications/unread-count", headers=auth_headers(user)).json()[
            "data"
        ]["count"]
        == 0
    )


def test_mark_read_ignores_ids_belonging_to_other_users(db: Session) -> None:
    """mark_read only updates notifications owned by the given recipient_id."""
    institution = make_institution(db)
    alice = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])
    bob = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    alice_notif = notif_service.create_notification(
        db, recipient_id=alice.id, title="Alice's", kind="INFO"
    )
    bob_notif = notif_service.create_notification(
        db, recipient_id=bob.id, title="Bob's", kind="INFO"
    )
    db.commit()

    # Alice tries to mark Bob's notification as read — it must be ignored.
    n = notif_service.mark_read(db, recipient_id=alice.id, ids=[bob_notif.id])
    assert n == 0

    db.refresh(bob_notif)
    assert bob_notif.is_read is False

    db.refresh(alice_notif)
    assert alice_notif.is_read is False

    # Alice marks her own — works.
    n = notif_service.mark_read(db, recipient_id=alice.id, ids=[alice_notif.id])
    assert n == 1


def test_unread_only_filter(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    user = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    n1 = notif_service.create_notification(db, recipient_id=user.id, title="Read", kind="INFO")
    notif_service.create_notification(db, recipient_id=user.id, title="Unread", kind="INFO")
    db.commit()
    notif_service.mark_read(db, recipient_id=user.id, ids=[n1.id])

    response = api_client.get("/api/v1/notifications?unread_only=true", headers=auth_headers(user))
    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["title"] == "Unread"


# --------------------------------------------------------------------------- outbox processing


def test_outbox_enqueue_is_idempotent(db: Session) -> None:
    """Enqueuing the same event twice does not create a duplicate outbox entry."""
    entry1 = notif_service.enqueue_notification_event(
        db,
        event_type="order.accepted",
        entity_type="print_order",
        entity_id="order-123",
        payload={"recipient_id": str(uuid.uuid4()), "body": "Order accepted"},
    )
    assert entry1 is not None
    db.flush()

    entry2 = notif_service.enqueue_notification_event(
        db,
        event_type="order.accepted",
        entity_type="print_order",
        entity_id="order-123",
        payload={"recipient_id": str(uuid.uuid4()), "body": "Order accepted"},
    )
    assert entry2 is None

    count = db.scalar(select(__import__("sqlalchemy").func.count()).select_from(NotificationOutbox))
    assert count == 1


def test_process_pending_outbox_creates_notifications(db: Session) -> None:
    institution = make_institution(db)
    user = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    notif_service.enqueue_notification_event(
        db,
        event_type="order.ready",
        entity_type="print_order",
        entity_id="order-456",
        payload={
            "recipient_id": str(user.id),
            "body": "Your order is ready",
            "institution_id": str(institution.id),
            "entity_id": "order-456",
        },
    )
    db.commit()

    processed = notif_service.process_pending_outbox(db)
    assert processed == 1

    notifications = list(
        db.scalars(select(Notification).where(Notification.recipient_id == user.id))
    )
    assert len(notifications) == 1
    assert notifications[0].title == "Print order ready for pickup"
    assert notifications[0].kind == "SUCCESS"

    # The outbox entry should be PROCESSED.
    entry = db.scalar(select(NotificationOutbox).where(NotificationOutbox.entity_id == "order-456"))
    assert entry is not None
    assert entry.status == "PROCESSED"


def test_processing_outbox_twice_does_not_duplicate(db: Session) -> None:
    """Processing the outbox a second time must not create duplicate notifications."""
    institution = make_institution(db)
    user = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    notif_service.enqueue_notification_event(
        db,
        event_type="order.completed",
        entity_type="print_order",
        entity_id="order-789",
        payload={
            "recipient_id": str(user.id),
            "body": "Done",
            "institution_id": str(institution.id),
            "entity_id": "order-789",
        },
    )
    db.commit()

    notif_service.process_pending_outbox(db)
    # Second call: no PENDING entries remain.
    processed = notif_service.process_pending_outbox(db)
    assert processed == 0

    count = db.scalar(
        select(__import__("sqlalchemy").func.count())
        .select_from(Notification)
        .where(Notification.recipient_id == user.id)
    )
    assert count == 1


def test_process_outbox_requires_analytics_permission(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    student = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])
    admin = make_user(db, roles=[("ADMIN", institution.id)])

    # Student lacks analytics:read.
    response = api_client.post(
        "/api/v1/notifications/process-outbox", headers=auth_headers(student)
    )
    assert response.status_code == 403

    # Admin has analytics:read (via ADMIN role).
    response = api_client.post("/api/v1/notifications/process-outbox", headers=auth_headers(admin))
    assert response.status_code == 200
