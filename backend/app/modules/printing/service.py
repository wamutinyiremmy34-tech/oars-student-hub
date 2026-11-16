"""Student-facing print ordering: upload, quote, order, cancel, track."""

import base64
import hashlib
import hmac
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import BinaryIO

from fastapi import UploadFile
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import BadRequestError, ConflictError, NotFoundError, UnsupportedMediaTypeError
from app.core.http import RequestMeta
from app.modules.audit import service as audit
from app.modules.files.models import StoredFile
from app.modules.files.service import store_upload
from app.modules.files.validation import FileKind
from app.modules.payments import service as payments
from app.modules.payments.models import Payment
from app.modules.printing import schemas
from app.modules.printing.models import (
    OrderStatusHistory,
    PrintDocument,
    PrintOrder,
    PrintOrderItem,
    PrintShop,
)
from app.modules.printing.pricing import ItemSpec, PricingError, Quote, Rule, quote_items
from app.modules.printing.shops import active_rules
from app.modules.printing.state import OrderStatus, PaymentStatus, can_transition
from app.modules.rbac.principal import Principal
from app.providers.scanner import MalwareScanner
from app.providers.storage.base import StorageBackend

S = OrderStatus
PRINTABLE_EXTS = frozenset({"pdf", "png", "jpg"})
LIVE_STATUSES = (S.SUBMITTED, S.ACCEPTED, S.PRINTING, S.READY_FOR_PICKUP)


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- pickup code


def pickup_code(order_id: uuid.UUID, secret: bytes) -> str:
    """Derived, not stored: HMAC(secret, order id). The student sees it when the order is ready and the
    operator must enter it to hand the documents over."""
    digest = hmac.new(secret, f"pickup:{order_id}".encode(), hashlib.sha256).digest()
    return base64.b32encode(digest)[:6].decode()


def pickup_secret(settings: Settings) -> bytes:
    return settings.jwt_secret_key.get_secret_value().encode()


# --------------------------------------------------------------------------- documents


def count_pages(stream: BinaryIO, kind: FileKind, max_pages: int) -> int:
    """Page count is decided by the SERVER (it drives the price), never taken from the client."""
    if kind.ext in ("png", "jpg"):
        return 1
    try:
        reader = PdfReader(stream, strict=False)
        if reader.is_encrypted:
            raise BadRequestError(
                "Password-protected PDFs can't be printed. Remove the password and upload again.",
                code="encrypted_pdf",
            )
        pages = len(reader.pages)
    except BadRequestError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf raises many error types for damaged files
        raise UnsupportedMediaTypeError(
            "This PDF could not be read.", code="unreadable_pdf"
        ) from exc
    if pages < 1:
        raise BadRequestError("This PDF has no pages.", code="unreadable_pdf")
    if pages > max_pages:
        raise BadRequestError(
            f"Documents can have at most {max_pages} pages.", code="too_many_pages"
        )
    return pages


def upload_document(
    db: Session, principal: Principal, upload: UploadFile, *, storage: StorageBackend,
    scanner: MalwareScanner, settings: Settings, meta: RequestMeta,
) -> tuple[PrintDocument, StoredFile]:  # fmt: skip
    counted: list[int] = []

    def inspect(stream: BinaryIO, kind: FileKind) -> None:
        counted.append(count_pages(stream, kind, settings.max_print_pages_per_document))

    stored = store_upload(
        db, upload=upload, owner_id=principal.user.id, key_prefix=f"print/{principal.user.id}",
        storage=storage, scanner=scanner, max_bytes=settings.max_upload_bytes,
        allowed_exts=PRINTABLE_EXTS, inspect=inspect,
    )  # fmt: skip
    document = PrintDocument(student_id=principal.user.id, file_id=stored.id, page_count=counted[0])
    db.add(document)
    db.flush()
    audit.record(db, action="print.document_uploaded", actor_user_id=principal.user.id, target_type="print_document",
                 target_id=str(document.id), details={"pages": document.page_count, "bytes": stored.size_bytes}, meta=meta)  # fmt: skip
    db.commit()
    return document, stored


# --------------------------------------------------------------------------- quoting


def _open_shop(db: Session, shop_id: uuid.UUID) -> PrintShop:
    shop = db.get(PrintShop, shop_id)
    if shop is None or not shop.is_active:
        raise BadRequestError("That print shop is not available.", code="invalid_shop")
    return shop


def _rules(db: Session, shop_id: uuid.UUID) -> list[Rule]:
    return [
        Rule(id=str(r.id), kind=r.kind, paper_size=r.paper_size, color_mode=r.color_mode, duplex=r.duplex,
             option_key=r.option_key, amount_ugx=r.amount_ugx)
        for r in active_rules(db, shop_id)
    ]  # fmt: skip


def _load_documents(
    db: Session, student_id: uuid.UUID, items: Sequence[schemas.ItemIn]
) -> dict[uuid.UUID, tuple[PrintDocument, StoredFile]]:
    ids = [i.document_id for i in items]
    rows = db.execute(
        select(PrintDocument, StoredFile).join(StoredFile, StoredFile.id == PrintDocument.file_id)
        .where(PrintDocument.id.in_(ids), PrintDocument.student_id == student_id, PrintDocument.purged_at.is_(None))
    ).all()  # fmt: skip
    found = {doc.id: (doc, stored) for doc, stored in rows}
    if set(found) != set(ids):  # someone else's document looks exactly like a missing one
        raise BadRequestError(
            "One of the documents could not be found. Upload it again.", code="invalid_document"
        )
    used = db.scalar(
        select(PrintOrderItem.document_id).where(PrintOrderItem.document_id.in_(ids)).limit(1)
    )
    if used is not None:
        raise BadRequestError(
            "A document can only be used in one order. Upload it again to reuse it.",
            code="document_already_used",
        )
    return found


def _specs(
    items: Sequence[schemas.ItemIn], docs: dict[uuid.UUID, tuple[PrintDocument, StoredFile]]
) -> list[ItemSpec]:
    return [
        ItemSpec(page_count=docs[i.document_id][0].page_count, copies=i.copies, paper_size=i.paper_size,
                 color_mode=i.color_mode, duplex=i.duplex, options=i.options)
        for i in items
    ]  # fmt: skip


def _price(rules: list[Rule], specs: list[ItemSpec]) -> Quote:
    try:
        return quote_items(rules, specs)
    except PricingError as exc:
        raise BadRequestError(exc.message, code=exc.code) from exc


def quote(db: Session, principal: Principal, data: schemas.QuoteIn) -> schemas.QuoteOut:
    shop = _open_shop(db, data.shop_id)
    principal.require("order:create", shop.institution_id)
    docs = _load_documents(db, principal.user.id, data.items)
    specs = _specs(data.items, docs)
    priced = _price(_rules(db, shop.id), specs)
    return schemas.QuoteOut(
        shop_id=shop.id, currency="UGX", total_ugx=priced.total_ugx,
        items=[
            schemas.QuoteItemOut(
                document_id=i.document_id, filename=docs[i.document_id][1].original_filename, page_count=s.page_count,
                copies=s.copies, paper_size=s.paper_size, color_mode=s.color_mode, duplex=s.duplex,
                options={k: v for k, v in s.options.items() if v}, unit_price_ugx=q.unit_price_ugx,
                line_total_ugx=q.line_total_ugx, lines=list(q.lines),
            )
            for i, s, q in zip(data.items, specs, priced.items, strict=True)
        ],
        order_lines=list(priced.order_lines),
    )  # fmt: skip


# --------------------------------------------------------------------------- ordering


def _check_limits(
    db: Session,
    student_id: uuid.UUID,
    shop: PrintShop,
    method: str,
    total: int,
    settings: Settings,
    *,
    exclude: uuid.UUID | None = None,
) -> None:
    ignore = exclude or uuid.UUID(int=0)
    active = db.scalar(select(func.count()).select_from(PrintOrder).where(
        PrintOrder.student_id == student_id, PrintOrder.status.in_(LIVE_STATUSES), PrintOrder.id != ignore))  # fmt: skip
    if (active or 0) >= settings.max_active_orders_per_student:
        raise ConflictError(
            "You have too many open orders. Wait for some to finish first.",
            code="too_many_active_orders",
        )
    if method != "PAY_ON_PICKUP":
        return
    if not shop.pay_on_pickup_enabled:
        raise ConflictError(
            "This shop doesn't accept pay-on-pickup. Please pay online.",
            code="pay_on_pickup_disabled",
        )
    limit = (
        shop.max_outstanding_pickup_orders
        if shop.max_outstanding_pickup_orders is not None
        else settings.max_outstanding_pickup_orders
    )
    outstanding = db.scalar(select(func.count()).select_from(PrintOrder).where(
        PrintOrder.student_id == student_id, PrintOrder.payment_method == "PAY_ON_PICKUP",
        PrintOrder.status.in_(LIVE_STATUSES), PrintOrder.id != ignore))  # fmt: skip
    if (outstanding or 0) >= limit:
        raise ConflictError(
            f"You already have {outstanding} unpaid pick-up orders. Collect or cancel them first, or pay online.",
            code="too_many_pickup_orders",
        )
    if total > settings.max_pickup_order_total_ugx:
        raise ConflictError(
            f"Pay-on-pickup orders are limited to UGX {settings.max_pickup_order_total_ugx:,}. Please pay online.",
            code="pickup_order_too_large",
        )


def add_history(
    db: Session,
    order: PrintOrder,
    from_status: str | None,
    to_status: str,
    actor_id: uuid.UUID | None,
    note: str | None = None,
) -> None:
    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_id,
            note=note,
        )
    )


def move(
    db: Session, order: PrintOrder, target: str, actor_id: uuid.UUID | None, note: str | None = None
) -> None:
    """The ONLY way an order's status changes. Invalid transitions are refused."""
    if not can_transition(order.status, target):
        raise ConflictError(
            f"An order that is {order.status.lower().replace('_', ' ')} can't become {target.lower().replace('_', ' ')}.",
            code="invalid_transition",
        )
    previous = order.status
    order.status = target
    if target in S.TERMINAL:
        order.closed_at = _now()
    add_history(db, order, previous, target, actor_id, note)


def create_order(
    db: Session, principal: Principal, data: schemas.OrderCreate, idempotency_key: str | None,
    settings: Settings, meta: RequestMeta,
) -> tuple[PrintOrder, bool]:  # fmt: skip
    """Returns (order, created). A replay of the same Idempotency-Key returns the original order."""
    user = principal.user
    shop = _open_shop(db, data.shop_id)
    principal.require("order:create", shop.institution_id)
    fp = payments.fingerprint(data.model_dump(mode="json", exclude={"expected_total_ugx"}))

    if idempotency_key:
        prior = db.scalar(
            select(PrintOrder).where(
                PrintOrder.student_id == user.id, PrintOrder.idempotency_key == idempotency_key
            )
        )
        if prior is not None:
            if prior.request_fingerprint != fp:
                raise ConflictError(
                    "That Idempotency-Key was already used for a different order.",
                    code="idempotency_key_reuse",
                )
            return prior, False

    if data.payment_method == "ONLINE" and not settings.payments_available:
        raise ConflictError(
            "Online payment isn't available yet. Choose pay-on-pickup.",
            code="online_payments_unavailable",
        )

    docs = _load_documents(db, user.id, data.items)
    specs = _specs(data.items, docs)
    priced = _price(_rules(db, shop.id), specs)  # the server's price; the client's is never read
    if data.expected_total_ugx is not None and data.expected_total_ugx != priced.total_ugx:
        raise ConflictError(
            f"The price changed to UGX {priced.total_ugx:,}. Please review your order.",
            code="price_changed",
        )
    _check_limits(db, user.id, shop, data.payment_method, priced.total_ugx, settings)

    status = S.DRAFT if data.draft else S.SUBMITTED
    order = PrintOrder(
        student_id=user.id, shop_id=shop.id, institution_id=shop.institution_id, status=status,
        payment_method=data.payment_method, payment_status=PaymentStatus.UNPAID, total_ugx=priced.total_ugx,
        price_snapshot=priced.snapshot(specs), note=data.note, idempotency_key=idempotency_key,
        request_fingerprint=fp, submitted_at=None if data.draft else _now(),
    )  # fmt: skip
    db.add(order)
    try:
        db.flush()
        for position, (item, spec, line) in enumerate(
            zip(data.items, specs, priced.items, strict=True)
        ):
            db.add(PrintOrderItem(
                order_id=order.id, position=position, document_id=item.document_id, copies=spec.copies,
                paper_size=spec.paper_size, color_mode=spec.color_mode, duplex=spec.duplex,
                options={k: v for k, v in spec.options.items() if v}, page_count=spec.page_count,
                unit_price_ugx=line.unit_price_ugx, line_total_ugx=line.line_total_ugx,
            ))  # fmt: skip
        add_history(db, order, None, status, user.id)
        audit.record(db, action="print.order_created", actor_user_id=user.id, target_type="print_order", target_id=str(order.id),
                     institution_id=order.institution_id, details={"total_ugx": order.total_ugx, "method": order.payment_method}, meta=meta)  # fmt: skip
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if idempotency_key:  # two identical requests raced: the loser returns the winner's order
            winner = db.scalar(
                select(PrintOrder).where(
                    PrintOrder.student_id == user.id, PrintOrder.idempotency_key == idempotency_key
                )
            )
            if winner is not None and winner.request_fingerprint == fp:
                return winner, False
        raise ConflictError(
            "Could not create the order. A document may already be in another order.",
            code="order_conflict",
        ) from exc
    return order, True


def own_order(
    db: Session, principal: Principal, order_id: uuid.UUID, *, lock: bool = False
) -> PrintOrder:
    stmt = select(PrintOrder).where(
        PrintOrder.id == order_id, PrintOrder.student_id == principal.user.id
    )
    order = db.scalar(stmt.with_for_update() if lock else stmt)
    if order is None:
        raise NotFoundError("Order not found.")  # another student's order does not exist for you
    return order


def submit_draft(
    db: Session, principal: Principal, order_id: uuid.UUID, settings: Settings, meta: RequestMeta
) -> PrintOrder:
    order = own_order(db, principal, order_id, lock=True)
    if order.status != S.DRAFT:
        raise ConflictError("Only a draft can be submitted.", code="invalid_transition")
    shop = _open_shop(db, order.shop_id)
    items = list(
        db.scalars(
            select(PrintOrderItem)
            .where(PrintOrderItem.order_id == order.id)
            .order_by(PrintOrderItem.position)
        )
    )
    specs = [
        ItemSpec(
            page_count=i.page_count,
            copies=i.copies,
            paper_size=i.paper_size,
            color_mode=i.color_mode,
            duplex=i.duplex,
            options=i.options,
        )
        for i in items
    ]
    priced = _price(_rules(db, shop.id), specs)  # re-price with TODAY's rules before it is binding
    if order.payment_method == "ONLINE" and not settings.payments_available:
        raise ConflictError(
            "Online payment isn't available yet.", code="online_payments_unavailable"
        )
    _check_limits(
        db,
        principal.user.id,
        shop,
        order.payment_method,
        priced.total_ugx,
        settings,
        exclude=order.id,
    )
    for item, line in zip(items, priced.items, strict=True):
        item.unit_price_ugx, item.line_total_ugx = line.unit_price_ugx, line.line_total_ugx
    order.total_ugx, order.price_snapshot, order.submitted_at = (
        priced.total_ugx,
        priced.snapshot(specs),
        _now(),
    )
    move(db, order, S.SUBMITTED, principal.user.id)
    audit.record(
        db,
        action="print.order_submitted",
        actor_user_id=principal.user.id,
        target_type="print_order",
        target_id=str(order.id),
        institution_id=order.institution_id,
        meta=meta,
    )
    db.commit()
    return order


def cancel_order(
    db: Session, principal: Principal, order_id: uuid.UUID, reason: str | None, meta: RequestMeta
) -> PrintOrder:
    order = own_order(db, principal, order_id, lock=True)
    if order.status not in S.STUDENT_CANCELLABLE:
        raise ConflictError("This order can't be cancelled any more.", code="not_cancellable")
    move(db, order, S.CANCELLED, principal.user.id, reason)
    order.cancel_reason = reason
    payments.settle_closed_order(db, order, "Order cancelled by the student", principal.user.id)
    audit.record(
        db,
        action="print.order_cancelled",
        actor_user_id=principal.user.id,
        target_type="print_order",
        target_id=str(order.id),
        institution_id=order.institution_id,
        meta=meta,
    )
    db.commit()
    return order


def list_orders(
    db: Session, principal: Principal, status: str | None, page: int, page_size: int
) -> tuple[list[PrintOrder], int]:
    stmt = select(PrintOrder).where(PrintOrder.student_id == principal.user.id)
    if status:
        stmt = stmt.where(PrintOrder.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(PrintOrder.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )
    return list(rows), total


# --------------------------------------------------------------------------- presentation


def order_out(
    db: Session,
    order: PrintOrder,
    settings: Settings,
    *,
    as_owner: bool,
    student_name: str | None = None,
) -> schemas.OrderOut:
    shop = db.get(PrintShop, order.shop_id)
    assert shop is not None
    rows = db.execute(
        select(PrintOrderItem, PrintDocument, StoredFile)
        .join(PrintDocument, PrintDocument.id == PrintOrderItem.document_id)
        .join(StoredFile, StoredFile.id == PrintDocument.file_id)
        .where(PrintOrderItem.order_id == order.id).order_by(PrintOrderItem.position)
    ).all()  # fmt: skip
    history = db.scalars(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order.id)
        .order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)
    )
    payment = db.scalar(
        select(Payment)
        .where(Payment.print_order_id == order.id)
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    return schemas.OrderOut(
        id=order.id, status=order.status, payment_method=order.payment_method, payment_status=order.payment_status,
        total_ugx=order.total_ugx,
        shop=schemas.ShopOut(id=shop.id, institution_id=shop.institution_id, name=shop.name, location=shop.location, is_active=shop.is_active, pay_on_pickup_enabled=shop.pay_on_pickup_enabled),
        items=[
            schemas.OrderItemOut(
                id=i.id, position=i.position, filename=stored.original_filename, page_count=i.page_count, copies=i.copies,
                paper_size=i.paper_size, color_mode=i.color_mode, duplex=i.duplex, options=i.options,
                unit_price_ugx=i.unit_price_ugx, line_total_ugx=i.line_total_ugx, document_available=doc.purged_at is None,
            )
            for i, doc, stored in rows
        ],
        history=[schemas.HistoryOut(from_status=h.from_status, to_status=h.to_status, note=h.note, created_at=h.created_at) for h in history],
        payment=None if payment is None else schemas.PaymentSummary(
            id=payment.id, status=payment.status, method=payment.method, amount_ugx=payment.amount_ugx,
            checkout_url=payment.checkout_url if payment.status == PaymentStatus.PENDING else None,
            created_at=payment.created_at, paid_at=payment.paid_at,
        ),
        note=order.note, reject_reason=order.reject_reason, cancel_reason=order.cancel_reason,
        # Only the owner ever sees the code, and only once the order is ready for collection.
        pickup_code=pickup_code(order.id, pickup_secret(settings)) if as_owner and order.status == S.READY_FOR_PICKUP else None,
        can_cancel=as_owner and order.status in S.STUDENT_CANCELLABLE,
        awaiting_payment=order.payment_method == "ONLINE" and order.status == S.SUBMITTED and order.payment_status in (PaymentStatus.UNPAID, PaymentStatus.FAILED, PaymentStatus.PENDING),
        created_at=order.created_at, student_name=student_name,
        retention_hold=None if as_owner else order.retention_hold,
    )  # fmt: skip


def summaries(
    db: Session, orders: Sequence[PrintOrder], *, with_student: bool = False
) -> list[schemas.OrderSummary]:
    if not orders:
        return []
    ids = [o.id for o in orders]
    shops = dict(
        db.execute(
            select(PrintShop.id, PrintShop.name).where(
                PrintShop.id.in_({o.shop_id for o in orders})
            )
        ).all()
    )
    counts = dict(
        db.execute(
            select(PrintOrderItem.order_id, func.count())
            .where(PrintOrderItem.order_id.in_(ids))
            .group_by(PrintOrderItem.order_id)
        ).all()
    )
    names: dict[uuid.UUID, str] = {}
    if with_student:
        from app.modules.users.models import User

        names = dict(
            db.execute(
                select(User.id, User.full_name).where(User.id.in_({o.student_id for o in orders}))
            ).all()
        )
    return [
        schemas.OrderSummary(
            id=o.id, status=o.status, payment_method=o.payment_method, payment_status=o.payment_status, total_ugx=o.total_ugx,
            shop_name=shops.get(o.shop_id, ""), item_count=counts.get(o.id, 0), created_at=o.created_at,
            student_name=names.get(o.student_id) if with_student else None,
        )
        for o in orders
    ]  # fmt: skip
