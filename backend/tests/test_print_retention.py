"""Retention: documents are purged only when nothing needs them any more."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import PrintCampus, auth_headers, fake_provider, new_order, op, upload_doc, v1
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit.models import AuditLog
from app.modules.files.models import StoredFile
from app.modules.payments.models import Payment, Refund
from app.modules.printing.models import PrintDocument, PrintOrder, PrintOrderItem
from app.modules.printing.retention import purge_expired_documents
from app.providers.storage.base import StorageError

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> PrintCampus:
    return PrintCampus(db)


def rejected_order(client: TestClient, c: PrintCampus, db: Session, user=None):  # type: ignore[no-untyped-def]
    order = new_order(client, user or c.student, c.shop, pages=2)
    assert (
        op(client, c.operator, order["id"], "reject", {"reason": "Not printable here"}).status_code
        == 200
    )
    row = db.get(PrintOrder, uuid.UUID(order["id"]))
    db.refresh(row)
    return row


def doc_of(db: Session, order: PrintOrder) -> PrintDocument:
    return db.scalar(
        select(PrintDocument)
        .join(PrintOrderItem, PrintOrderItem.document_id == PrintDocument.id)
        .where(PrintOrderItem.order_id == order.id)
    )


def purge(db: Session, storage, now):  # type: ignore[no-untyped-def]
    return purge_expired_documents(db, storage, get_settings(), now=now)


def test_documents_are_deleted_after_the_retention_period(
    api_client: TestClient, campus: PrintCampus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    order = rejected_order(api_client, campus, db)
    document = doc_of(db, order)
    key = db.get(StoredFile, document.file_id).storage_key
    days = get_settings().print_retention_days

    early = purge(db, storage, order.closed_at + timedelta(days=days - 1))
    assert early.total == 0 and document.purged_at is None
    assert b"".join(storage.open(key)).startswith(b"%PDF")  # still there

    report = purge(db, storage, order.closed_at + timedelta(days=days + 1))
    assert (report.closed_orders, report.orphans, report.storage_errors) == (1, 0, 0)
    db.refresh(document)
    assert document.purged_at is not None
    with pytest.raises(StorageError):
        storage.open(key)
    assert (
        db.scalar(select(PrintOrderItem).where(PrintOrderItem.order_id == order.id)) is not None
    )  # the order record stays
    assert "print.documents_purged" in db.scalars(select(AuditLog.action)).all()
    assert purge(db, storage, order.closed_at + timedelta(days=days + 2)).total == 0  # idempotent


def test_a_retention_hold_blocks_deletion_until_cleared(
    api_client: TestClient, campus: PrintCampus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    order = rejected_order(api_client, campus, db)
    later = order.closed_at + timedelta(days=get_settings().print_retention_days + 1)
    held = api_client.post(
        v1(f"/operator/orders/{order.id}/hold"),
        json={"hold": True, "reason": "dispute"},
        headers=auth_headers(campus.admin),
    )
    assert held.status_code == 200
    assert purge(db, storage, later).total == 0
    api_client.post(
        v1(f"/operator/orders/{order.id}/hold"),
        json={"hold": False},
        headers=auth_headers(campus.admin),
    )
    assert purge(db, storage, later).closed_orders == 1


def test_unresolved_payments_and_refunds_block_deletion(
    api_client: TestClient, campus: PrintCampus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    later_days = get_settings().print_retention_days + 1

    # a refund still waiting to be processed
    paid = new_order(api_client, campus.student, campus.shop, pages=1, method="ONLINE")
    created = api_client.post(
        v1("/payments"), json={"order_id": paid["id"]}, headers=auth_headers(campus.student)
    ).json()["data"]
    payment = db.get(Payment, uuid.UUID(created["id"]))
    fake_provider(api_client).set_status(payment.provider_reference, "PAID")
    api_client.post(v1(f"/payments/{payment.id}/verify"), headers=auth_headers(campus.student))
    api_client.post(
        v1(f"/print/orders/{paid['id']}/cancel"), json={}, headers=auth_headers(campus.student)
    )
    order = db.get(PrintOrder, uuid.UUID(paid["id"]))
    db.refresh(order)
    assert db.scalar(select(Refund)).status == "REQUESTED"
    assert (
        purge(db, storage, order.closed_at + timedelta(days=later_days)).total == 0
    )  # the refund is still open

    api_client.post(v1(f"/payments/{payment.id}/refund"), headers=auth_headers(campus.admin))
    assert (
        purge(db, storage, order.closed_at + timedelta(days=later_days)).closed_orders == 1
    )  # resolved, so now deletable

    # a payment that is still pending on a closed order
    other = rejected_order(api_client, campus, db, user=campus.student2)
    db.add(
        Payment(
            payer_user_id=other.student_id,
            purpose="PRINT_ORDER",
            print_order_id=other.id,
            amount_ugx=100,
            method="ONLINE",
            provider="fake",
            status="PENDING",
        )
    )
    db.commit()
    assert purge(db, storage, other.closed_at + timedelta(days=later_days)).total == 0


def test_active_orders_are_never_purged(
    api_client: TestClient, campus: PrintCampus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    order = new_order(api_client, campus.student, campus.shop)
    far_future = db.get(PrintOrder, uuid.UUID(order["id"])).created_at + timedelta(days=400)
    assert purge(db, storage, far_future).total == 0
    for action in ("accept", "printing", "ready"):
        op(api_client, campus.operator, order["id"], action)
    assert purge(db, storage, far_future).total == 0  # READY_FOR_PICKUP is not closed


def test_unused_uploads_are_purged_but_attached_ones_are_not(
    api_client: TestClient, campus: PrintCampus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    orphan_id = upload_doc(api_client, campus.student).json()["data"]["id"]
    attached = new_order(api_client, campus.student, campus.shop)
    orphan = db.get(PrintDocument, uuid.UUID(orphan_id))
    hours = get_settings().print_orphan_upload_hours

    assert purge(db, storage, orphan.created_at + timedelta(hours=hours - 1)).total == 0
    report = purge(db, storage, orphan.created_at + timedelta(hours=hours + 1))
    assert (report.closed_orders, report.orphans) == (0, 1)
    db.refresh(orphan)
    assert orphan.purged_at is not None
    assert doc_of(db, db.get(PrintOrder, uuid.UUID(attached["id"]))).purged_at is None


def test_a_storage_failure_leaves_the_document_for_the_next_run(
    api_client: TestClient, campus: PrintCampus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    order = rejected_order(api_client, campus, db)
    document = doc_of(db, order)
    later = order.closed_at + timedelta(days=get_settings().print_retention_days + 1)

    class Broken:
        def delete(self, key: str) -> None:
            raise OSError("disk offline")

    report = purge_expired_documents(db, Broken(), get_settings(), now=later)  # type: ignore[arg-type]
    assert (report.total, report.storage_errors) == (0, 1)
    db.refresh(document)
    assert document.purged_at is None  # not marked deleted when it was not
    assert purge(db, storage, later).closed_orders == 1  # the next run succeeds
