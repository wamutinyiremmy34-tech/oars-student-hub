"""Database invariants for printing and payments: they hold even if application code is wrong."""

import uuid
from datetime import UTC, datetime

import pytest
from helpers import PrintCampus, make_resource, make_user, put_file
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.payments.models import Payment, PaymentEvent, Refund
from app.modules.printing.models import (
    OrderStatusHistory,
    PrintDocument,
    PrintOrder,
    PrintOrderItem,
    PrintPricingRule,
)
from app.modules.rbac.models import Permission, Role, RolePermission

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> PrintCampus:
    return PrintCampus(db)


def _fail(db: Session, *objects: object) -> None:
    with pytest.raises(IntegrityError):
        db.add_all(objects)
        db.flush()
    db.rollback()


def order_row(c: PrintCampus, **overrides: object) -> PrintOrder:
    fields: dict[str, object] = {
        "student_id": c.student.id, "shop_id": c.shop.id, "institution_id": c.inst.id,
        "status": "SUBMITTED", "payment_method": "PAY_ON_PICKUP", "payment_status": "UNPAID",
        "total_ugx": 100, "price_snapshot": {},
    }  # fmt: skip
    return PrintOrder(**{**fields, **overrides})  # type: ignore[arg-type]


def saved_order(c: PrintCampus, **overrides: object) -> PrintOrder:
    order = order_row(c, **overrides)
    c.db.add(order)
    c.db.commit()
    return order


def payment_row(order: PrintOrder, **overrides: object) -> Payment:
    fields: dict[str, object] = {
        "payer_user_id": order.student_id, "purpose": "PRINT_ORDER", "print_order_id": order.id,
        "amount_ugx": order.total_ugx, "method": "ONLINE", "provider": "fake", "status": "PENDING",
    }  # fmt: skip
    return Payment(**{**fields, **overrides})  # type: ignore[arg-type]


# --------------------------------------------------------------------------- order invariants


def test_a_completed_order_must_be_paid(db: Session, campus: PrintCampus) -> None:
    _fail(db, order_row(campus, status="COMPLETED", payment_status="UNPAID"))
    _fail(db, order_row(campus, status="COMPLETED", payment_status="PENDING"))
    saved_order(campus, status="COMPLETED", payment_status="PAID")


def test_an_online_order_cannot_progress_without_payment(db: Session, campus: PrintCampus) -> None:
    for status in ("ACCEPTED", "PRINTING", "READY_FOR_PICKUP"):
        _fail(
            db, order_row(campus, payment_method="ONLINE", status=status, payment_status="UNPAID")
        )
    saved_order(campus, payment_method="ONLINE", status="ACCEPTED", payment_status="PAID")
    saved_order(
        campus, payment_method="ONLINE", status="SUBMITTED", payment_status="UNPAID"
    )  # waiting for payment is fine
    saved_order(campus, payment_method="ONLINE", status="CANCELLED", payment_status="UNPAID")
    saved_order(
        campus, payment_method="PAY_ON_PICKUP", status="ACCEPTED", payment_status="UNPAID"
    )  # cash is collected later


def test_an_orders_shop_must_belong_to_its_institution(db: Session, campus: PrintCampus) -> None:
    _fail(db, order_row(campus, institution_id=campus.inst_b.id))  # shop is in inst, not inst_b


@pytest.mark.parametrize(
    "fields",
    [
        {"total_ugx": 0},
        {"total_ugx": -5},
        {"status": "SHIPPED"},
        {"payment_status": "MAYBE"},
        {"payment_method": "BARTER"},
    ],
)
def test_order_check_constraints(
    db: Session, campus: PrintCampus, fields: dict[str, object]
) -> None:
    _fail(db, order_row(campus, **fields))


def test_idempotency_keys_are_unique_per_student(db: Session, campus: PrintCampus) -> None:
    saved_order(campus, idempotency_key="key-000001")
    saved_order(campus, idempotency_key=None)
    saved_order(campus, idempotency_key=None)  # NULL keys never clash
    _fail(db, order_row(campus, idempotency_key="key-000001"))
    saved_order(campus, student_id=campus.student2.id, idempotency_key="key-000001")


def test_item_constraints_and_one_order_per_document(
    db: Session, campus: PrintCampus, storage
) -> None:  # type: ignore[no-untyped-def]
    order = saved_order(campus)

    def document() -> PrintDocument:
        doc = PrintDocument(
            student_id=campus.student.id,
            file_id=put_file(db, storage, campus.student).id,
            page_count=2,
        )
        db.add(doc)
        db.flush()
        return doc

    def item(doc: PrintDocument, position: int = 0, **over: object) -> PrintOrderItem:
        fields: dict[str, object] = {
            "order_id": order.id, "position": position, "document_id": doc.id, "copies": 1, "paper_size": "A4",
            "color_mode": "BW", "duplex": False, "options": {}, "page_count": 2, "unit_price_ugx": 50, "line_total_ugx": 100,
        }  # fmt: skip
        return PrintOrderItem(**{**fields, **over})  # type: ignore[arg-type]

    first = document()
    db.commit()
    for bad in (
        {"copies": 0},
        {"copies": 101},
        {"color_mode": "SEPIA"},
        {"page_count": 0},
        {"unit_price_ugx": -1},
    ):
        _fail(db, item(first, **bad))
    db.add(item(first))
    db.commit()
    _fail(db, item(document(), position=0))  # position already used in this order
    second = document()
    db.commit()
    _fail(db, item(first, position=1))  # the same document cannot be in two items
    db.add(item(second, position=1))
    db.commit()


def test_documents_need_at_least_one_page(db: Session, campus: PrintCampus, storage) -> None:  # type: ignore[no-untyped-def]
    _fail(
        db,
        PrintDocument(
            student_id=campus.student.id,
            file_id=put_file(db, storage, campus.student).id,
            page_count=0,
        ),
    )


def test_deleting_an_order_removes_its_items_and_history_but_never_its_payments(
    db: Session, campus: PrintCampus
) -> None:
    order = saved_order(campus)
    db.add(OrderStatusHistory(order_id=order.id, from_status=None, to_status="SUBMITTED"))
    db.commit()
    paid = saved_order(campus)
    db.add(payment_row(paid))
    db.commit()
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT: payment records outlive everything
        db.execute(text("DELETE FROM print_orders WHERE id = :id"), {"id": paid.id})
    db.rollback()
    db.execute(text("DELETE FROM print_orders WHERE id = :id"), {"id": order.id})
    assert (
        db.execute(
            text("SELECT count(*) FROM order_status_history WHERE order_id = :id"), {"id": order.id}
        ).scalar_one()
        == 0
    )


@pytest.mark.parametrize("status", ["SHIPPED", "", "submitted"])
def test_history_statuses_are_constrained(db: Session, campus: PrintCampus, status: str) -> None:
    order = saved_order(campus)
    _fail(db, OrderStatusHistory(order_id=order.id, from_status=None, to_status=status))


# --------------------------------------------------------------------------- pricing rules


@pytest.mark.parametrize(
    "fields",
    [
        {
            "kind": "PER_PAGE",
            "paper_size": None,
            "color_mode": "BW",
            "amount_ugx": 50,
        },  # needs a paper size
        {"kind": "PER_PAGE", "paper_size": "A4", "color_mode": None, "amount_ugx": 50},
        {
            "kind": "PER_PAGE",
            "paper_size": "A4",
            "color_mode": "BW",
            "amount_ugx": 0,
        },  # a page cannot be free
        {
            "kind": "PER_PAGE",
            "paper_size": "A4",
            "color_mode": "BW",
            "amount_ugx": 50,
            "option_key": "staple",
        },
        {"kind": "PER_COPY", "amount_ugx": 100},  # extras need an option key
        {"kind": "PER_ORDER", "amount_ugx": 100, "option_key": None},
        {"kind": "PER_COPY", "option_key": "staple", "amount_ugx": -1},
        {"kind": "PER_PAGE", "paper_size": "A4", "color_mode": "SEPIA", "amount_ugx": 50},
        {"kind": "BULK", "option_key": "x", "amount_ugx": 5},
    ],
)
def test_pricing_rule_shapes_are_enforced(
    db: Session, campus: PrintCampus, fields: dict[str, object]
) -> None:
    _fail(db, PrintPricingRule(shop_id=campus.shop.id, **fields))
    db.add(
        PrintPricingRule(
            shop_id=campus.shop.id, kind="PER_COPY", option_key="laminate", amount_ugx=0
        )
    )  # a free extra is fine
    db.commit()


# --------------------------------------------------------------------------- payment invariants


def test_only_one_live_payment_per_order(db: Session, campus: PrintCampus) -> None:
    order = saved_order(campus, payment_method="ONLINE")
    first = payment_row(order)
    db.add(first)
    db.commit()
    _fail(db, payment_row(order))  # a second PENDING
    first.status = "FAILED"
    db.commit()
    retry = payment_row(order)
    db.add(retry)
    db.commit()  # after a failure a new attempt is allowed
    retry.status = "PAID"
    db.commit()
    _fail(db, payment_row(order))  # nothing can be live next to a PAID payment


def test_only_one_live_purchase_per_user_and_resource(
    db: Session, campus: PrintCampus, storage
) -> None:  # type: ignore[no-untyped-def]
    provider = make_user(db, roles=[("RESOURCE_PROVIDER", campus.inst.id)])
    resource = make_resource(
        db,
        provider=provider,
        institution=campus.inst,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
    )

    def purchase(user) -> Payment:  # type: ignore[no-untyped-def]
        return Payment(
            payer_user_id=user.id,
            purpose="RESOURCE_PURCHASE",
            resource_id=resource.id,
            amount_ugx=5000,
            method="ONLINE",
            provider="fake",
            status="PENDING",
        )

    db.add(purchase(campus.student))
    db.commit()
    _fail(db, purchase(campus.student))
    db.add(purchase(campus.student2))  # another buyer is independent
    db.commit()


def test_cash_and_method_rules(db: Session, campus: PrintCampus) -> None:
    order = saved_order(campus)
    _fail(
        db, payment_row(order, method="PAY_ON_PICKUP", provider="CASH", status="PENDING")
    )  # cash is never pending
    _fail(
        db, payment_row(order, method="ONLINE", provider="CASH", status="PAID")
    )  # online cannot be cash
    _fail(
        db, payment_row(order, method="PAY_ON_PICKUP", provider="fake", status="PAID")
    )  # cash method needs the CASH provider
    db.add(payment_row(order, method="PAY_ON_PICKUP", provider="CASH", status="PAID"))
    db.commit()


def test_a_payment_pays_for_exactly_one_thing_and_amounts_are_positive(
    db: Session, campus: PrintCampus, storage
) -> None:  # type: ignore[no-untyped-def]
    order = saved_order(campus)
    provider = make_user(db, roles=[("RESOURCE_PROVIDER", campus.inst.id)])
    resource = make_resource(
        db,
        provider=provider,
        institution=campus.inst,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
    )
    _fail(db, payment_row(order, print_order_id=None))  # PRINT_ORDER without an order
    _fail(db, payment_row(order, resource_id=resource.id))  # both targets
    _fail(db, payment_row(order, purpose="RESOURCE_PURCHASE"))  # purpose and target disagree
    _fail(db, payment_row(order, amount_ugx=0))
    _fail(db, payment_row(order, currency="USD"))
    _fail(db, payment_row(order, status="PAUSED"))
    _fail(db, payment_row(order, purpose="GIFT"))


def test_provider_references_and_idempotency_keys_are_unique(
    db: Session, campus: PrintCampus
) -> None:
    orders = [saved_order(campus, payment_method="ONLINE") for _ in range(3)]
    db.add(payment_row(orders[0], provider_reference="ref-1", idempotency_key="idem-0001"))
    db.commit()
    _fail(
        db, payment_row(orders[1], provider_reference="ref-1")
    )  # a provider reference identifies ONE payment
    _fail(db, payment_row(orders[1], idempotency_key="idem-0001"))
    db.add(
        payment_row(orders[1], provider="other", provider_reference="ref-1")
    )  # same string at another provider is fine
    db.add(payment_row(orders[2], payer_user_id=campus.student2.id, idempotency_key="idem-0001"))
    db.commit()


def test_webhook_events_are_unique_per_provider_event_id(db: Session) -> None:
    def event(provider: str = "fake", event_id: str = "evt-1") -> PaymentEvent:
        return PaymentEvent(
            provider=provider,
            provider_event_id=event_id,
            event_type="payment.succeeded",
            payload={},
        )

    db.add(event())
    db.commit()
    _fail(db, event())  # the replay is refused by the database itself
    db.add_all([event(event_id="evt-2"), event(provider="other")])
    db.commit()
    _fail(
        db,
        PaymentEvent(
            provider="fake",
            provider_event_id="evt-9",
            event_type="x",
            payload={},
            processing_status="WEIRD",
        ),
    )


def test_a_payment_can_only_be_refunded_once(db: Session, campus: PrintCampus) -> None:
    order = saved_order(campus, payment_method="ONLINE", status="CANCELLED", payment_status="PAID")
    payment = payment_row(order, status="PAID")
    db.add(payment)
    db.commit()

    def refund(status: str) -> Refund:
        return Refund(payment_id=payment.id, amount_ugx=100, reason="r", status=status)

    db.add(refund("FAILED"))
    db.commit()  # failed attempts do not block a retry
    db.add(refund("REQUESTED"))
    db.commit()
    _fail(db, refund("REQUESTED"))
    _fail(db, refund("SUCCEEDED"))  # open or completed: only one
    _fail(db, Refund(payment_id=payment.id, amount_ugx=0, reason="r", status="FAILED"))


def test_new_permissions_are_granted_to_the_right_roles(db: Session) -> None:
    def codes(role: str) -> set[str]:
        return set(db.scalars(
            select(Permission.code).join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id).where(Role.name == role)))  # fmt: skip

    assert "payment:create" in codes("STUDENT") and "payment:record_cash" not in codes("STUDENT")
    assert "payment:record_cash" in codes("PRINTING_OPERATOR") and "payment:create" not in codes(
        "PRINTING_OPERATOR"
    )
    assert {
        "printshop:manage",
        "order:manage_any",
        "payment:create",
        "payment:record_cash",
        "payment:manage",
    } <= codes("ADMIN")
    assert "resource:review_own" not in codes("ADMIN")
    assert not {"printshop:manage", "order:manage_any", "payment:manage"} & (
        codes("STUDENT") | codes("PRINTING_OPERATOR")
    )
    assert datetime.now(UTC) and uuid.uuid4()  # (imports used by sibling tests)
