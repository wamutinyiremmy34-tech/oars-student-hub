"""Operator workflow: authorization per shop, valid transitions, pay-on-pickup, document access."""

import uuid

import pytest
from fastapi.testclient import TestClient
from helpers import PrintCampus, auth_headers, new_order, op, pickup_code_for, run_to_ready, v1
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog
from app.modules.payments.models import Payment
from app.modules.printing.models import OrderStatusHistory, PrintDocument, PrintOrder

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> PrintCampus:
    return PrintCampus(db)


def actions(db: Session, order_id) -> list[str]:  # type: ignore[no-untyped-def]
    return list(
        db.scalars(
            select(AuditLog.action)
            .where(AuditLog.target_id == str(order_id))
            .order_by(AuditLog.created_at)
        )
    )


def test_pay_on_pickup_end_to_end(api_client: TestClient, campus: PrintCampus, db: Session) -> None:
    c, client = campus, api_client
    order = new_order(client, c.student, c.shop, pages=3, copies=2)  # UGX 300
    oid = order["id"]
    assert (order["payment_method"], order["payment_status"]) == ("PAY_ON_PICKUP", "UNPAID")

    queue = client.get(v1("/operator/orders"), headers=auth_headers(c.operator)).json()
    assert [o["id"] for o in queue["data"]] == [oid] and queue["data"][0]["student_name"]

    run_to_ready(client, c.operator, oid)
    code = pickup_code_for(oid)
    done_too_early = op(client, c.operator, oid, "complete", {"pickup_code": code})
    assert (done_too_early.status_code, done_too_early.json()["error"]["code"]) == (
        409,
        "payment_required",
    )  # not paid yet
    assert (
        op(client, c.operator, oid, "complete", {"pickup_code": "WRONG1"}).json()["error"]["code"]
        == "invalid_pickup_code"
    )

    assert (
        op(client, c.operator, oid, "payment", {"amount_ugx": 250}).json()["error"]["code"]
        == "amount_mismatch"
    )
    paid = op(client, c.operator, oid, "payment", {"amount_ugx": 300})
    assert paid.status_code == 200 and paid.json()["data"]["payment_status"] == "PAID"
    assert (
        op(client, c.operator, oid, "payment", {"amount_ugx": 300}).json()["error"]["code"]
        == "already_paid"
    )

    assert op(client, c.operator, oid, "complete", {"pickup_code": "WRONG1"}).status_code == 403
    finished = op(
        client, c.operator, oid, "complete", {"pickup_code": code.lower()}
    )  # case-insensitive
    assert finished.status_code == 200 and finished.json()["data"]["status"] == "COMPLETED"

    payment = db.scalar(select(Payment).where(Payment.print_order_id == uuid.UUID(oid)))
    assert (payment.provider, payment.method, payment.status, payment.amount_ugx) == (
        "CASH",
        "PAY_ON_PICKUP",
        "PAID",
        300,
    )
    assert payment.recorded_by_user_id == c.operator.id and payment.paid_at is not None
    assert db.scalar(select(func.count()).select_from(Payment)) == 1
    assert "payment.cash_recorded" in actions(db, oid) and "print.pickup_code_rejected" in actions(
        db, oid
    )
    history = list(
        db.scalars(
            select(OrderStatusHistory.to_status)
            .where(OrderStatusHistory.order_id == uuid.UUID(oid))
            .order_by(OrderStatusHistory.created_at)
        )
    )
    assert history == ["SUBMITTED", "ACCEPTED", "PRINTING", "READY_FOR_PICKUP", "COMPLETED"]
    mine = client.get(v1(f"/print/orders/{oid}"), headers=auth_headers(c.student)).json()["data"]
    assert (
        mine["status"] == "COMPLETED"
        and mine["payment_status"] == "PAID"
        and mine["pickup_code"] is None
    )


def test_cash_can_only_be_recorded_for_a_ready_pay_on_pickup_order(
    api_client: TestClient, campus: PrintCampus
) -> None:
    c, client = campus, api_client
    order = new_order(client, c.student, c.shop, pages=1)
    assert (
        op(client, c.operator, order["id"], "payment", {"amount_ugx": 50}).json()["error"]["code"]
        == "invalid_transition"
    )
    online = new_order(client, c.student2, c.shop, pages=1, method="ONLINE")
    assert (
        op(client, c.operator, online["id"], "payment", {"amount_ugx": 50}).status_code == 409
    )  # online orders are not paid in cash


@pytest.mark.parametrize(
    ("path", "action", "body"),
    [
        (["accept"], "accept", None),
        ([], "printing", None),
        ([], "ready", None),
        ([], "complete", {"pickup_code": "ABCDEF"}),
        (["accept"], "ready", None),
        (["accept", "printing"], "accept", None),
        (["accept", "printing"], "reject", {"reason": "too late"}),
        (["accept", "printing"], "complete", {"pickup_code": "ABCDEF"}),
        (["accept", "printing", "ready"], "printing", None),
        (["accept", "printing", "ready"], "reject", {"reason": "nope"}),
    ],
)
def test_invalid_transitions_are_refused(
    api_client: TestClient, campus: PrintCampus, db: Session, path: list[str], action: str, body
) -> None:  # type: ignore[no-untyped-def]
    order = new_order(api_client, campus.student, campus.shop)
    for step in path:
        assert op(api_client, campus.operator, order["id"], step).status_code == 200
    response = op(api_client, campus.operator, order["id"], action, body)
    assert response.status_code == 409, response.text
    assert (
        db.get(PrintOrder, uuid.UUID(order["id"])).reject_reason is None
    )  # a refused request changed nothing


def test_terminal_orders_cannot_move_again(api_client: TestClient, campus: PrintCampus) -> None:
    order = new_order(api_client, campus.student, campus.shop)
    assert (
        op(
            api_client, campus.operator, order["id"], "reject", {"reason": "Colour not available"}
        ).json()["data"]["status"]
        == "REJECTED"
    )
    for action in ("accept", "printing", "ready"):
        assert op(api_client, campus.operator, order["id"], action).status_code == 409
    seen = api_client.get(
        v1(f"/print/orders/{order['id']}"), headers=auth_headers(campus.student)
    ).json()["data"]
    assert seen["reject_reason"] == "Colour not available"
    assert (
        op(api_client, campus.operator, order["id"], "reject", {"reason": "x"}).status_code == 422
    )  # a real reason is required


def test_operators_only_see_their_own_shops_orders(
    api_client: TestClient, campus: PrintCampus
) -> None:
    c, client = campus, api_client
    order = new_order(client, c.student, c.shop)
    detail = v1(f"/operator/orders/{order['id']}")

    assert client.get(detail, headers=auth_headers(c.operator)).status_code == 200
    for outsider in (c.operator2, c.operator_b, c.stray_operator, c.admin_b):
        assert (
            client.get(detail, headers=auth_headers(outsider)).status_code == 404
        )  # other shop, other university, no shop
        assert op(client, outsider, order["id"], "accept").status_code == 404
        assert (
            client.get(v1("/operator/orders"), headers=auth_headers(outsider)).json()["data"] == []
        )
    assert client.get(v1("/operator/shops"), headers=auth_headers(c.operator)).json()["data"][0][
        "id"
    ] == str(c.shop.id)
    assert (
        client.get(v1("/operator/shops"), headers=auth_headers(c.stray_operator)).json()["data"]
        == []
    )


def test_administrators_can_act_within_their_institution_only(
    api_client: TestClient, campus: PrintCampus
) -> None:
    c, client = campus, api_client
    order = new_order(client, c.student, c.shop)
    assert (
        op(client, c.admin, order["id"], "accept").status_code == 200
    )  # order:manage_any in this institution
    other = new_order(client, c.student2, c.shop)
    assert op(client, c.platform, other["id"], "accept").status_code == 200
    third = new_order(client, c.student2, c.shop2)
    assert op(client, c.admin_b, third["id"], "accept").status_code == 404


def test_customers_cannot_use_operator_endpoints(
    api_client: TestClient, campus: PrintCampus
) -> None:
    order = new_order(api_client, campus.student, campus.shop)
    assert (
        api_client.get(v1("/operator/orders"), headers=auth_headers(campus.student)).status_code
        == 403
    )
    assert op(api_client, campus.student, order["id"], "accept").status_code == 403
    assert api_client.get(v1("/operator/orders")).status_code == 401


def test_only_managers_can_set_a_retention_hold(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    order = new_order(api_client, campus.student, campus.shop)
    hold = {"hold": True, "reason": "payment dispute"}
    assert (
        api_client.post(
            v1(f"/operator/orders/{order['id']}/hold"),
            json=hold,
            headers=auth_headers(campus.operator),
        ).status_code
        == 403
    )
    assert (
        api_client.post(
            v1(f"/operator/orders/{order['id']}/hold"),
            json=hold,
            headers=auth_headers(campus.admin_b),
        ).status_code
        == 404
    )
    assert (
        api_client.post(
            v1(f"/operator/orders/{order['id']}/hold"),
            json=hold,
            headers=auth_headers(campus.admin),
        ).status_code
        == 200
    )
    assert db.get(PrintOrder, uuid.UUID(order["id"])).retention_hold is True


def test_operators_get_audited_short_lived_links_to_the_documents(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    c, client = campus, api_client
    order = new_order(client, c.student, c.shop)
    item_id = client.get(
        v1(f"/operator/orders/{order['id']}"), headers=auth_headers(c.operator)
    ).json()["data"]["items"][0]["id"]
    url = v1(f"/operator/orders/{order['id']}/items/{item_id}/document-link")

    link = client.post(url, headers=auth_headers(c.operator))
    assert link.status_code == 200 and link.json()["data"]["expires_in"] == 60
    assert "print/" not in link.text  # no storage key
    assert client.get(link.json()["data"]["url"]).content.startswith(b"%PDF")
    assert "print.document_accessed" in actions(
        db, order["id"]
    )  # who looked at a student's document is recorded

    assert client.post(url, headers=auth_headers(c.operator2)).status_code == 404
    assert client.post(url, headers=auth_headers(c.student)).status_code == 403
    assert (
        client.post(
            v1(
                f"/operator/orders/{order['id']}/items/00000000-0000-0000-0000-000000000001/document-link"
            ),
            headers=auth_headers(c.operator),
        ).status_code
        == 404
    )


def test_purged_documents_have_no_link(
    api_client: TestClient, campus: PrintCampus, db: Session
) -> None:
    from datetime import UTC, datetime

    order = new_order(api_client, campus.student, campus.shop)
    db.scalar(select(PrintDocument)).purged_at = datetime.now(UTC)
    db.commit()
    detail = api_client.get(
        v1(f"/operator/orders/{order['id']}"), headers=auth_headers(campus.operator)
    ).json()["data"]
    assert detail["items"][0]["document_available"] is False
    url = v1(f"/operator/orders/{order['id']}/items/{detail['items'][0]['id']}/document-link")
    gone = api_client.post(url, headers=auth_headers(campus.operator))
    assert (gone.status_code, gone.json()["error"]["code"]) == (404, "document_purged")
