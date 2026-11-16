"""Quotes and orders: server-side pricing, snapshots, idempotency, isolation, abuse limits."""

import uuid

import pytest
from fastapi.testclient import TestClient
from helpers import (
    PrintCampus,
    auth_headers,
    make_client,
    make_shop,
    new_order,
    op,
    order_body,
    place_order,
    upload_doc,
    v1,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.printing.models import (
    OrderStatusHistory,
    PrintOrder,
    PrintOrderItem,
    PrintPricingRule,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> PrintCampus:
    return PrintCampus(db)


def quote(client: TestClient, user, shop, doc_ids, **item):  # type: ignore[no-untyped-def]
    return client.post(
        v1("/print/quote"), json=order_body(shop, doc_ids, **item), headers=auth_headers(user)
    )


def count(db: Session, model) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(model)) or 0


# --------------------------------------------------------------------------- quotes


def test_the_quote_is_calculated_by_the_server_from_the_rules(
    api_client: TestClient, campus: PrintCampus
) -> None:
    doc = upload_doc(api_client, campus.student, pages=3).json()["data"]["id"]
    response = quote(api_client, campus.student, campus.shop, [doc], copies=2)
    assert response.status_code == 200
    data = response.json()["data"]
    assert (
        data["total_ugx"] == 3 * 2 * 50 and data["currency"] == "UGX"
    )  # 3 pages x 2 copies x UGX 50
    item = data["items"][0]
    assert (item["page_count"], item["unit_price_ugx"], item["line_total_ugx"]) == (3, 50, 300)

    duplex = quote(api_client, campus.student, campus.shop, [doc], copies=2, duplex=True).json()[
        "data"
    ]
    assert duplex["total_ugx"] == 3 * 2 * 40
    extras = quote(
        api_client,
        campus.student,
        campus.shop,
        [doc],
        copies=2,
        options={"staple": True, "binding": True},
    ).json()["data"]
    assert extras["total_ugx"] == 300 + 2 * 100 + 2000
    assert [line["label"] for line in extras["order_lines"]] == ["binding"]


@pytest.mark.parametrize(
    ("item", "code"),
    [
        ({"paper_size": "A5"}, "unsupported_combination"),
        ({"options": {"laminate": True}}, "unsupported_option"),
    ],
)
def test_options_the_shop_does_not_offer_are_refused(
    api_client: TestClient, campus: PrintCampus, item: dict, code: str
) -> None:  # type: ignore[type-arg]
    doc = upload_doc(api_client, campus.student).json()["data"]["id"]
    response = quote(api_client, campus.student, campus.shop, [doc], **item)
    assert (response.status_code, response.json()["error"]["code"]) == (400, code)


@pytest.mark.parametrize(
    "item",
    [{"copies": 0}, {"copies": 101}, {"color_mode": "SEPIA"}, {"options": {"Bad Key!": True}}],
)
def test_invalid_print_options_are_rejected_at_the_edge(
    api_client: TestClient, campus: PrintCampus, item: dict
) -> None:  # type: ignore[type-arg]
    doc = upload_doc(api_client, campus.student).json()["data"]["id"]
    assert quote(api_client, campus.student, campus.shop, [doc], **item).status_code == 422


def test_quotes_need_a_valid_shop_and_login(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    doc = upload_doc(api_client, campus.student).json()["data"]["id"]
    assert (
        api_client.post(v1("/print/quote"), json=order_body(campus.shop, [doc])).status_code == 401
    )
    campus.shop.is_active = False
    db.commit()
    assert (
        quote(api_client, campus.student, campus.shop, [doc]).json()["error"]["code"]
        == "invalid_shop"
    )
    # a student of institution A cannot order from institution B's shop
    assert quote(api_client, campus.student, campus.shop_b, [doc]).status_code == 403


# --------------------------------------------------------------------------- creating orders


def test_the_client_cannot_set_the_price(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    doc = upload_doc(api_client, campus.student, pages=2).json()["data"]["id"]
    response = place_order(
        api_client,
        campus.student,
        campus.shop,
        [doc],
        extra={"total_ugx": 1, "price": 1, "unit_price_ugx": 1},
    )
    assert response.status_code == 201
    assert response.json()["data"]["total_ugx"] == 100  # the server's number, not 1
    assert db.scalar(select(PrintOrder.total_ugx)) == 100


def test_a_stale_expected_total_is_a_conflict_not_a_price(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    doc = upload_doc(api_client, campus.student, pages=2).json()["data"]["id"]
    wrong = place_order(
        api_client, campus.student, campus.shop, [doc], extra={"expected_total_ugx": 1}
    )
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (409, "price_changed")
    assert count(db, PrintOrder) == 0
    right = place_order(
        api_client, campus.student, campus.shop, [doc], extra={"expected_total_ugx": 100}
    )
    assert right.status_code == 201


def test_the_order_stores_everything_needed_to_reproduce_the_price(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    data = new_order(
        api_client,
        campus.student,
        campus.shop,
        pages=4,
        copies=3,
        duplex=True,
        options={"staple": True, "binding": True},
    )
    order = db.get(PrintOrder, uuid.UUID(data["id"]))
    snapshot = order.price_snapshot
    rule_ids = {str(r.id) for r in db.scalars(select(PrintPricingRule))}

    assert snapshot["total_ugx"] == order.total_ugx == 4 * 3 * 40 + 3 * 100 + 2000
    item = snapshot["items"][0]
    assert (item["page_count"], item["copies"], item["duplex"], item["unit_price_ugx"]) == (
        4,
        3,
        True,
        40,
    )
    assert item["page_rule_id"] in rule_ids and all(
        line["rule_id"] in rule_ids for line in item["lines"] + snapshot["order_lines"]
    )
    rebuilt = sum(line["amount_ugx"] for it in snapshot["items"] for line in it["lines"]) + sum(
        line["amount_ugx"] for line in snapshot["order_lines"]
    )
    assert rebuilt == order.total_ugx
    row = db.scalar(select(PrintOrderItem))
    assert (row.page_count, row.copies, row.unit_price_ugx, row.line_total_ugx) == (
        4,
        3,
        40,
        4 * 3 * 40 + 3 * 100,
    )
    history = db.scalars(
        select(OrderStatusHistory.to_status).where(OrderStatusHistory.order_id == order.id)
    ).all()
    assert history == ["SUBMITTED"]


def test_changing_the_shops_prices_later_does_not_change_existing_orders(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    data = new_order(api_client, campus.student, campus.shop, pages=10)
    assert data["total_ugx"] == 500
    rule = db.scalar(
        select(PrintPricingRule).where(
            PrintPricingRule.shop_id == campus.shop.id,
            PrintPricingRule.color_mode == "BW",
            PrintPricingRule.duplex.is_(None),
        )
    )
    changed = api_client.patch(
        v1(f"/print/shops/{campus.shop.id}/pricing-rules/{rule.id}"),
        json={"amount_ugx": 999},
        headers=auth_headers(campus.admin),
    )
    assert changed.status_code == 200
    assert (
        api_client.get(
            v1(f"/print/orders/{data['id']}"), headers=auth_headers(campus.student)
        ).json()["data"]["total_ugx"]
        == 500
    )
    assert (
        new_order(api_client, campus.student2, campus.shop, pages=10)["total_ugx"] == 9990
    )  # new orders use the new price


def test_idempotency_key_makes_retries_safe(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    doc = upload_doc(api_client, campus.student).json()["data"]["id"]
    first = place_order(api_client, campus.student, campus.shop, [doc], key="retry-key-0001")
    again = place_order(api_client, campus.student, campus.shop, [doc], key="retry-key-0001")
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["data"]["id"] == again.json()["data"]["id"]
    assert count(db, PrintOrder) == 1 and count(db, PrintOrderItem) == 1

    other_doc = upload_doc(api_client, campus.student, pages=9).json()["data"]["id"]
    clash = place_order(api_client, campus.student, campus.shop, [other_doc], key="retry-key-0001")
    assert (clash.status_code, clash.json()["error"]["code"]) == (409, "idempotency_key_reuse")
    # keys are per student: another student reusing the string gets their own order
    doc2 = upload_doc(api_client, campus.student2).json()["data"]["id"]
    assert (
        place_order(
            api_client, campus.student2, campus.shop, [doc2], key="retry-key-0001"
        ).status_code
        == 201
    )


def test_a_document_belongs_to_one_order(api_client: TestClient, campus: PrintCampus) -> None:
    doc = upload_doc(api_client, campus.student).json()["data"]["id"]
    assert place_order(api_client, campus.student, campus.shop, [doc]).status_code == 201
    second = place_order(api_client, campus.student, campus.shop2, [doc])
    assert second.status_code == 400 and second.json()["error"]["code"] == "document_already_used"


def test_drafts_are_invisible_to_the_shop_until_submitted_and_repriced_then(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    doc = upload_doc(api_client, campus.student, pages=10).json()["data"]["id"]
    draft = place_order(
        api_client, campus.student, campus.shop, [doc], extra={"draft": True}
    ).json()["data"]
    assert draft["status"] == "DRAFT"
    assert (
        op(api_client, campus.operator, draft["id"], "accept").status_code == 404
    )  # not visible to operators
    assert (
        api_client.get(v1("/operator/orders"), headers=auth_headers(campus.operator)).json()["data"]
        == []
    )

    rule = db.scalar(
        select(PrintPricingRule).where(
            PrintPricingRule.shop_id == campus.shop.id,
            PrintPricingRule.color_mode == "BW",
            PrintPricingRule.duplex.is_(None),
        )
    )
    rule.amount_ugx = 60
    db.commit()
    submitted = api_client.post(
        v1(f"/print/orders/{draft['id']}/submit"), headers=auth_headers(campus.student)
    ).json()["data"]
    assert (
        submitted["status"] == "SUBMITTED" and submitted["total_ugx"] == 600
    )  # re-priced with today's rules
    assert (
        api_client.post(
            v1(f"/print/orders/{draft['id']}/submit"), headers=auth_headers(campus.student)
        ).status_code
        == 409
    )


# --------------------------------------------------------------------------- isolation and cancellation


def test_students_only_ever_see_their_own_orders(
    api_client: TestClient, campus: PrintCampus
) -> None:
    mine = new_order(api_client, campus.student, campus.shop)
    theirs = new_order(api_client, campus.student2, campus.shop)
    other = auth_headers(campus.student2)
    assert api_client.get(v1(f"/print/orders/{mine['id']}"), headers=other).status_code == 404
    assert (
        api_client.post(
            v1(f"/print/orders/{mine['id']}/cancel"), json={}, headers=other
        ).status_code
        == 404
    )
    assert (
        api_client.post(v1(f"/print/orders/{mine['id']}/submit"), headers=other).status_code == 404
    )
    listing = api_client.get(v1("/print/orders"), headers=other).json()
    assert [o["id"] for o in listing["data"]] == [theirs["id"]] and listing["meta"]["total"] == 1
    assert api_client.get(v1(f"/print/orders/{mine['id']}")).status_code == 401


def test_the_pickup_code_is_shown_only_to_the_owner_and_only_when_ready(
    api_client: TestClient, campus: PrintCampus
) -> None:
    order = new_order(api_client, campus.student, campus.shop)
    assert order["pickup_code"] is None
    for action in ("accept", "printing"):
        op(api_client, campus.operator, order["id"], action)
    assert (
        api_client.get(
            v1(f"/print/orders/{order['id']}"), headers=auth_headers(campus.student)
        ).json()["data"]["pickup_code"]
        is None
    )
    op(api_client, campus.operator, order["id"], "ready")
    mine = api_client.get(
        v1(f"/print/orders/{order['id']}"), headers=auth_headers(campus.student)
    ).json()["data"]
    seen_by_operator = api_client.get(
        v1(f"/operator/orders/{order['id']}"), headers=auth_headers(campus.operator)
    ).json()["data"]
    assert len(mine["pickup_code"]) == 6 and seen_by_operator["pickup_code"] is None


def test_students_can_cancel_only_until_printing_starts(
    api_client: TestClient, campus: PrintCampus
) -> None:
    headers = auth_headers(campus.student)
    submitted = new_order(api_client, campus.student, campus.shop)
    cancelled = api_client.post(
        v1(f"/print/orders/{submitted['id']}/cancel"),
        json={"reason": "changed my mind"},
        headers=headers,
    )
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert (
        api_client.post(
            v1(f"/print/orders/{submitted['id']}/cancel"), json={}, headers=headers
        ).status_code
        == 409
    )

    accepted = new_order(api_client, campus.student, campus.shop)
    op(api_client, campus.operator, accepted["id"], "accept")
    assert (
        api_client.post(
            v1(f"/print/orders/{accepted['id']}/cancel"), json={}, headers=headers
        ).status_code
        == 200
    )  # ACCEPTED is still cancellable

    printing = new_order(api_client, campus.student, campus.shop)
    op(api_client, campus.operator, printing["id"], "accept")
    op(api_client, campus.operator, printing["id"], "printing")
    refused = api_client.post(
        v1(f"/print/orders/{printing['id']}/cancel"), json={}, headers=headers
    )
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "not_cancellable")


# --------------------------------------------------------------------------- pay-on-pickup abuse controls


def test_outstanding_pickup_orders_are_limited_but_online_orders_are_not(
    api_client: TestClient, campus: PrintCampus
) -> None:
    new_order(api_client, campus.student, campus.shop)
    new_order(api_client, campus.student, campus.shop)  # the default limit is 2
    doc = upload_doc(api_client, campus.student).json()["data"]["id"]
    third = place_order(api_client, campus.student, campus.shop, [doc])
    assert (third.status_code, third.json()["error"]["code"]) == (409, "too_many_pickup_orders")
    assert (
        place_order(api_client, campus.student, campus.shop, [doc], "ONLINE").status_code == 201
    )  # paying online is always allowed
    assert (
        new_order(api_client, campus.student2, campus.shop)["status"] == "SUBMITTED"
    )  # limits are per student


def test_cancelling_frees_a_pickup_slot(api_client: TestClient, campus: PrintCampus) -> None:
    first = new_order(api_client, campus.student, campus.shop)
    new_order(api_client, campus.student, campus.shop)
    api_client.post(
        v1(f"/print/orders/{first['id']}/cancel"), json={}, headers=auth_headers(campus.student)
    )
    assert new_order(api_client, campus.student, campus.shop)["status"] == "SUBMITTED"


def test_pickup_limits_are_configurable(
    db: Session, campus: PrintCampus, storage, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    client = make_client(
        db, storage, monkeypatch, MAX_PICKUP_ORDER_TOTAL_UGX=1000, MAX_OUTSTANDING_PICKUP_ORDERS=5
    )
    small = new_order(client, campus.student, campus.shop, pages=2)  # UGX 100
    assert small["total_ugx"] == 100
    doc = upload_doc(client, campus.student, pages=30).json()["data"]["id"]  # UGX 1,500 > cap
    big = place_order(client, campus.student, campus.shop, [doc])
    assert (big.status_code, big.json()["error"]["code"]) == (409, "pickup_order_too_large")
    assert place_order(client, campus.student, campus.shop, [doc], "ONLINE").status_code == 201


def test_a_shop_can_override_or_disable_pay_on_pickup(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    strict = make_shop(db, campus.inst, max_outstanding_pickup_orders=0)
    doc = upload_doc(api_client, campus.student).json()["data"]["id"]
    assert (
        place_order(api_client, campus.student, strict, [doc]).json()["error"]["code"]
        == "too_many_pickup_orders"
    )
    closed = make_shop(db, campus.inst, pay_on_pickup_enabled=False)
    assert (
        place_order(api_client, campus.student, closed, [doc]).json()["error"]["code"]
        == "pay_on_pickup_disabled"
    )
    assert place_order(api_client, campus.student, closed, [doc], "ONLINE").status_code == 201


# --------------------------------------------------------------------------- shop administration


def test_shop_administration_is_scoped_to_the_institution(
    api_client: TestClient, campus: PrintCampus
) -> None:
    mine, other = auth_headers(campus.admin), auth_headers(campus.admin_b)
    created = api_client.post(
        v1("/print/shops"),
        json={"institution_id": str(campus.inst.id), "name": "Second Floor Shop"},
        headers=mine,
    )
    assert created.status_code == 201
    assert (
        api_client.post(
            v1("/print/shops"),
            json={"institution_id": str(campus.inst.id), "name": "Second Floor Shop"},
            headers=mine,
        ).status_code
        == 409
    )
    assert (
        api_client.post(
            v1("/print/shops"),
            json={"institution_id": str(campus.inst_b.id), "name": "Intruder"},
            headers=mine,
        ).status_code
        == 403
    )
    assert (
        api_client.patch(
            v1(f"/print/shops/{campus.shop.id}"), json={"name": "Hijacked"}, headers=other
        ).status_code
        == 404
    )
    assert (
        api_client.post(
            v1(f"/print/shops/{campus.shop.id}/staff"),
            json={"user_id": str(campus.operator.id)},
            headers=other,
        ).status_code
        == 404
    )
    assert (
        api_client.post(
            v1("/print/shops"),
            json={"institution_id": str(campus.inst.id), "name": "Student Shop"},
            headers=auth_headers(campus.student),
        ).status_code
        == 403
    )

    rule = api_client.post(
        v1(f"/print/shops/{campus.shop.id}/pricing-rules"),
        json={"kind": "PER_PAGE", "paper_size": "a3", "color_mode": "BW", "amount_ugx": 150},
        headers=mine,
    )
    assert rule.status_code == 201 and rule.json()["data"]["paper_size"] == "A3"
    duplicate = api_client.post(
        v1(f"/print/shops/{campus.shop.id}/pricing-rules"),
        json={"kind": "PER_PAGE", "paper_size": "A3", "color_mode": "BW", "amount_ugx": 160},
        headers=mine,
    )
    assert duplicate.status_code == 409  # two live rules would make the price ambiguous
    assert (
        api_client.post(
            v1(f"/print/shops/{campus.shop.id}/pricing-rules"),
            json={"kind": "PER_PAGE", "amount_ugx": 5},
            headers=mine,
        ).status_code
        == 422
    )

    prices = api_client.get(v1(f"/print/shops/{campus.shop.id}/pricing")).json()[
        "data"
    ]  # the price list is public
    assert any(r["paper_size"] == "A3" for r in prices)
    shops = api_client.get(
        v1("/print/shops"), params={"institution_id": str(campus.inst.id)}
    ).json()["data"]
    assert len(shops) >= 3  # several shops per institution are supported
