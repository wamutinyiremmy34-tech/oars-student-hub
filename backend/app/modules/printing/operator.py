"""Operator workflow. An operator sees and acts on the orders of the shops they are STAFF of
(and only if their role grants the permission for that institution). Administrators with
order:manage_any can act on any shop in their institution scope."""

import hmac
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.http import RequestMeta
from app.core.security import create_download_token
from app.modules.audit import service as audit
from app.modules.files.models import StoredFile
from app.modules.payments import service as payments
from app.modules.payments.models import Payment
from app.modules.printing import schemas
from app.modules.printing.models import (
    PrintDocument,
    PrintOrder,
    PrintOrderItem,
    PrintShop,
    PrintShopStaff,
)
from app.modules.printing.service import move, order_out, pickup_code, pickup_secret
from app.modules.printing.state import OrderStatus, PaymentStatus, can_order_pay_transition
from app.modules.rbac.principal import Principal
from app.modules.users.models import User
from app.providers.storage.base import StorageBackend

S = OrderStatus


def _has_access(db: Session, principal: Principal, shop: PrintShop, *, write: bool) -> bool:
    if principal.can("order:manage_any", shop.institution_id):
        return True
    permission = "order:update_status" if write else "order:read_any"
    is_staff = db.get(PrintShopStaff, (shop.id, principal.user.id)) is not None
    return is_staff and principal.can(permission, shop.institution_id)


def accessible_shops(db: Session, principal: Principal) -> list[PrintShop]:
    shops = db.scalars(
        select(PrintShop).where(PrintShop.is_active.is_(True)).order_by(PrintShop.name)
    )
    return [s for s in shops if _has_access(db, principal, s, write=False)]


def authorize(
    db: Session, principal: Principal, order_id: uuid.UUID, *, write: bool, lock: bool = False
) -> PrintOrder:
    stmt = select(PrintOrder).where(PrintOrder.id == order_id, PrintOrder.status != S.DRAFT)
    order = db.scalar(stmt.with_for_update() if lock else stmt)
    shop = db.get(PrintShop, order.shop_id) if order else None
    if order is None or shop is None or not _has_access(db, principal, shop, write=write):
        raise NotFoundError("Order not found.")  # another shop's order does not exist for you
    return order


def queue(
    db: Session,
    principal: Principal,
    shop_id: uuid.UUID | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[PrintOrder], int]:
    allowed = {s.id for s in accessible_shops(db, principal)}
    if shop_id is not None:
        allowed &= {shop_id}
    stmt = select(PrintOrder).where(PrintOrder.shop_id.in_(allowed), PrintOrder.status != S.DRAFT)
    stmt = (
        stmt.where(PrintOrder.status == status)
        if status
        else stmt.where(
            PrintOrder.status.in_((S.SUBMITTED, S.ACCEPTED, S.PRINTING, S.READY_FOR_PICKUP))
        )
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(PrintOrder.submitted_at.asc().nulls_last(), PrintOrder.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(rows), total


def detail(
    db: Session, principal: Principal, order_id: uuid.UUID, settings: Settings
) -> schemas.OrderOut:
    order = authorize(db, principal, order_id, write=False)
    student = db.get(User, order.student_id)
    return order_out(
        db, order, settings, as_owner=False, student_name=student.full_name if student else None
    )


def _finish(
    db: Session, principal: Principal, order: PrintOrder, action: str, meta: RequestMeta
) -> PrintOrder:
    audit.record(db, action=f"print.order_{action}", actor_user_id=principal.user.id, target_type="print_order",
                 target_id=str(order.id), institution_id=order.institution_id, meta=meta)  # fmt: skip
    db.commit()
    return order


def accept(db: Session, principal: Principal, order_id: uuid.UUID, meta: RequestMeta) -> PrintOrder:
    order = authorize(db, principal, order_id, write=True, lock=True)
    if order.payment_method == "ONLINE" and order.payment_status != PaymentStatus.PAID:
        raise ConflictError("Online payment has not been confirmed yet.", code="payment_required")
    move(db, order, S.ACCEPTED, principal.user.id)
    return _finish(db, principal, order, "accepted", meta)


def reject(
    db: Session, principal: Principal, order_id: uuid.UUID, reason: str, meta: RequestMeta
) -> PrintOrder:
    order = authorize(db, principal, order_id, write=True, lock=True)
    move(
        db, order, S.REJECTED, principal.user.id, reason
    )  # validates first, so a refused request changes nothing
    order.reject_reason = reason
    payments.settle_closed_order(db, order, f"Order rejected: {reason}", principal.user.id)
    return _finish(db, principal, order, "rejected", meta)


def start_printing(
    db: Session, principal: Principal, order_id: uuid.UUID, meta: RequestMeta
) -> PrintOrder:
    order = authorize(db, principal, order_id, write=True, lock=True)
    move(db, order, S.PRINTING, principal.user.id)
    return _finish(db, principal, order, "printing", meta)


def mark_ready(
    db: Session, principal: Principal, order_id: uuid.UUID, meta: RequestMeta
) -> PrintOrder:
    order = authorize(db, principal, order_id, write=True, lock=True)
    move(db, order, S.READY_FOR_PICKUP, principal.user.id)
    return _finish(db, principal, order, "ready", meta)


def record_cash(
    db: Session, principal: Principal, order_id: uuid.UUID, amount_ugx: int, meta: RequestMeta
) -> PrintOrder:
    """Pay-on-pickup, step 1 of 2: the operator took the money. Creates the payment record (provider CASH)."""
    order = authorize(db, principal, order_id, write=True, lock=True)
    principal.require("payment:record_cash", order.institution_id)
    if order.payment_method != "PAY_ON_PICKUP":
        raise ConflictError("This order is paid online.", code="not_pay_on_pickup")
    if order.status != S.READY_FOR_PICKUP:
        raise ConflictError(
            "Record the payment when the customer collects a ready order.",
            code="invalid_transition",
        )
    if order.payment_status == PaymentStatus.PAID:
        raise ConflictError("This order is already paid.", code="already_paid")
    if amount_ugx != order.total_ugx:
        raise ConflictError(f"The order total is UGX {order.total_ugx:,}.", code="amount_mismatch")
    if not can_order_pay_transition(order.payment_status, PaymentStatus.PAID):
        raise ConflictError("This payment can't be recorded.", code="invalid_transition")
    now = datetime.now(UTC)
    db.add(Payment(
        payer_user_id=order.student_id, purpose="PRINT_ORDER", print_order_id=order.id, amount_ugx=order.total_ugx,
        method="PAY_ON_PICKUP", provider="CASH", status=PaymentStatus.PAID, paid_at=now, recorded_by_user_id=principal.user.id,
    ))  # fmt: skip
    order.payment_status = PaymentStatus.PAID
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("This order is already paid.", code="already_paid") from exc
    audit.record(db, action="payment.cash_recorded", actor_user_id=principal.user.id, target_type="print_order",
                 target_id=str(order.id), institution_id=order.institution_id, details={"amount_ugx": order.total_ugx}, meta=meta)  # fmt: skip
    db.commit()
    return order


def complete(
    db: Session,
    principal: Principal,
    order_id: uuid.UUID,
    code: str,
    settings: Settings,
    meta: RequestMeta,
) -> PrintOrder:
    order = authorize(db, principal, order_id, write=True, lock=True)
    if order.status != S.READY_FOR_PICKUP:
        raise ConflictError("Only a ready order can be handed over.", code="invalid_transition")
    if not hmac.compare_digest(
        code.strip().upper(), pickup_code(order.id, pickup_secret(settings))
    ):
        audit.record(db, action="print.pickup_code_rejected", outcome="DENIED", actor_user_id=principal.user.id,
                     target_type="print_order", target_id=str(order.id), institution_id=order.institution_id, meta=meta)  # fmt: skip
        db.commit()
        raise ForbiddenError("That pickup code is not correct.", code="invalid_pickup_code")
    if (
        order.payment_status != PaymentStatus.PAID
    ):  # the database also refuses COMPLETED without PAID
        raise ConflictError(
            "Record the cash payment first."
            if order.payment_method == "PAY_ON_PICKUP"
            else "This order has not been paid.",
            code="payment_required",
        )
    move(db, order, S.COMPLETED, principal.user.id)
    return _finish(db, principal, order, "completed", meta)


def document_link(
    db: Session,
    principal: Principal,
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    storage: StorageBackend,
    meta: RequestMeta,
) -> schemas.LinkOut:
    """A short-lived link to ONE student document. Every access to a student's document is audited."""
    order = authorize(db, principal, order_id, write=False)
    row = db.execute(
        select(PrintOrderItem, PrintDocument, StoredFile)
        .join(PrintDocument, PrintDocument.id == PrintOrderItem.document_id)
        .join(StoredFile, StoredFile.id == PrintDocument.file_id)
        .where(PrintOrderItem.id == item_id, PrintOrderItem.order_id == order.id)
    ).one_or_none()  # fmt: skip
    if row is None:
        raise NotFoundError("Document not found.")
    _, document, stored = row
    if document.purged_at is not None:
        raise NotFoundError(
            "This document was deleted after the retention period.", code="document_purged"
        )
    settings = get_settings()
    ttl = settings.download_url_ttl_seconds
    url = storage.presigned_get_url(
        stored.storage_key,
        filename=stored.original_filename,
        content_type=stored.mime_type,
        expires_in=ttl,
    )
    if url is None:
        url = f"{settings.api_v1_prefix}/downloads/{create_download_token(user_id=str(principal.user.id), file_id=str(stored.id), ttl_seconds=ttl)}"
    audit.record(db, action="print.document_accessed", actor_user_id=principal.user.id, target_type="print_order",
                 target_id=str(order.id), institution_id=order.institution_id, details={"item_id": str(item_id)}, meta=meta)  # fmt: skip
    db.commit()
    return schemas.LinkOut(url=url, expires_in=ttl, filename=stored.original_filename)


def set_hold(
    db: Session,
    principal: Principal,
    order_id: uuid.UUID,
    hold: bool,
    reason: str | None,
    meta: RequestMeta,
) -> PrintOrder:
    order = db.get(PrintOrder, order_id)
    if order is None or not principal.can("order:manage_any", order.institution_id):
        raise NotFoundError("Order not found.")
    order.retention_hold, order.retention_hold_reason = hold, reason if hold else None
    return _finish(
        db, principal, order, "retention_hold_set" if hold else "retention_hold_cleared", meta
    )
