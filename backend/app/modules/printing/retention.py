"""Retention: student documents are deleted from storage after a configurable period.

A document is purged only when ALL of these hold, so nothing needed for a business or legal process
disappears early:
  * its order is in a terminal state (completed, cancelled or rejected) for at least PRINT_RETENTION_DAYS;
  * the order has no retention hold;
  * no payment for the order is still pending, and no refund for it is still waiting to be processed.
Uploads that never became part of an order are purged after PRINT_ORPHAN_UPLOAD_HOURS.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.audit import service as audit
from app.modules.files.models import StoredFile
from app.modules.payments.models import Payment, Refund
from app.modules.printing.models import PrintDocument, PrintOrder, PrintOrderItem
from app.modules.printing.state import OrderStatus
from app.providers.storage.base import StorageBackend

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurgeReport:
    closed_orders: int
    orphans: int
    storage_errors: int

    @property
    def total(self) -> int:
        return self.closed_orders + self.orphans


def purge_expired_documents(
    db: Session, storage: StorageBackend, settings: Settings, *, now: datetime | None = None
) -> PurgeReport:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=settings.print_retention_days)
    pending_payment = exists().where(
        Payment.print_order_id == PrintOrder.id, Payment.status == "PENDING"
    )
    open_refund = exists().where(
        Refund.payment_id == Payment.id,
        Payment.print_order_id == PrintOrder.id,
        Refund.status == "REQUESTED",
    )

    closed = db.scalars(
        select(PrintDocument)
        .join(PrintOrderItem, PrintOrderItem.document_id == PrintDocument.id)
        .join(PrintOrder, PrintOrder.id == PrintOrderItem.order_id)
        .where(
            PrintDocument.purged_at.is_(None),
            PrintOrder.status.in_(tuple(OrderStatus.TERMINAL)),
            PrintOrder.closed_at <= cutoff,
            PrintOrder.retention_hold.is_(False),
            ~pending_payment,
            ~open_refund,
        )
    ).all()
    orphan_cutoff = now - timedelta(hours=settings.print_orphan_upload_hours)
    orphans = db.scalars(
        select(PrintDocument).where(
            PrintDocument.purged_at.is_(None), PrintDocument.created_at <= orphan_cutoff,
            ~exists().where(PrintOrderItem.document_id == PrintDocument.id),
        )
    ).all()  # fmt: skip

    errors = purged_closed = purged_orphans = 0
    closed_ids = {d.id for d in closed}
    for document in [*closed, *orphans]:
        stored = db.get(StoredFile, document.file_id)
        try:
            if stored is not None:
                storage.delete(stored.storage_key)
        except Exception:  # noqa: BLE001 - keep going; the document stays un-purged and is retried next run
            logger.exception("print_document_purge_failed", extra={"document_id": str(document.id)})
            errors += 1
            continue
        document.purged_at = now
        if document.id in closed_ids:
            purged_closed += 1
        else:
            purged_orphans += 1
    report = PurgeReport(closed_orders=purged_closed, orphans=purged_orphans, storage_errors=errors)
    if report.total:
        audit.record(
            db,
            action="print.documents_purged",
            details={
                "closed_orders": report.closed_orders,
                "orphans": report.orphans,
                "errors": errors,
            },
        )
    db.commit()
    return report
