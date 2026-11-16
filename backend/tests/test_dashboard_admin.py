"""Dashboard and admin endpoint tests.

These are integration tests: they require a running PostgreSQL (docker compose up -d).
"""

import pytest
from fastapi.testclient import TestClient
from helpers import auth_headers, make_institution, make_user
from sqlalchemy.orm import Session

from app.modules.audit import service as audit
from app.modules.notifications import service as notif_service

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- dashboard


def test_dashboard_requires_authentication(api_client: TestClient) -> None:
    assert api_client.get("/api/v1/dashboard").status_code == 401


def test_student_dashboard_returns_personal_data(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    student = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    # Create a notification and a bookmark for the student.
    notif_service.create_notification(db, recipient_id=student.id, title="Welcome", kind="INFO")
    db.commit()

    response = api_client.get("/api/v1/dashboard", headers=auth_headers(student))
    assert response.status_code == 200
    data = response.json()["data"]
    assert student.full_name.split()[0] in data["greeting"]
    assert data["unread_notifications"] == 1
    assert data["bookmarked_count"] == 0
    assert isinstance(data["recent_resources"], list)
    assert isinstance(data["recent_orders"], list)


def test_dashboard_unread_count_reflects_read_state(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    student = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    n1 = notif_service.create_notification(db, recipient_id=student.id, title="N1", kind="INFO")
    notif_service.create_notification(db, recipient_id=student.id, title="N2", kind="INFO")
    db.commit()
    notif_service.mark_read(db, recipient_id=student.id, ids=[n1.id])

    response = api_client.get("/api/v1/dashboard", headers=auth_headers(student))
    assert response.json()["data"]["unread_notifications"] == 1


# --------------------------------------------------------------------------- admin: user list


def test_admin_user_list_requires_user_read_permission(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    student = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])
    admin = make_user(db, roles=[("ADMIN", institution.id)])
    platform_admin = make_user(db, roles=[("ADMIN", None)])

    # Student cannot list users.
    assert api_client.get("/api/v1/admin/users", headers=auth_headers(student)).status_code == 403

    # Institution-scoped admin can list users (within scope).
    response = api_client.get("/api/v1/admin/users", headers=auth_headers(admin))
    assert response.status_code == 200
    assert "items" in response.json()["data"]

    # Platform admin can also list users.
    assert (
        api_client.get("/api/v1/admin/users", headers=auth_headers(platform_admin)).status_code
        == 200
    )


def test_admin_user_list_search_and_pagination(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    admin = make_user(db, roles=[("ADMIN", None)])
    make_user(
        db, email="alice@example.com", institution=institution, roles=[("STUDENT", institution.id)]
    )
    make_user(
        db, email="bob@example.com", institution=institution, roles=[("STUDENT", institution.id)]
    )

    # Search by email fragment.
    response = api_client.get("/api/v1/admin/users?q=alice", headers=auth_headers(admin))
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["email"] == "alice@example.com"

    # Pagination.
    response = api_client.get("/api/v1/admin/users?page=1&page_size=1", headers=auth_headers(admin))
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["items"]) == 1
    assert data["total"] >= 2


# --------------------------------------------------------------------------- admin: audit logs


def test_audit_log_read_requires_audit_read_permission(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    student = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])
    admin = make_user(db, roles=[("ADMIN", institution.id)])

    # Create an audit log entry.
    audit.record(
        db,
        action="test.action",
        actor_user_id=admin.id,
        institution_id=institution.id,
        meta=None,
    )
    db.commit()

    # Student cannot read audit logs.
    assert (
        api_client.get("/api/v1/admin/audit-logs", headers=auth_headers(student)).status_code == 403
    )

    # Admin can.
    assert (
        api_client.get("/api/v1/admin/audit-logs", headers=auth_headers(admin)).status_code == 200
    )


def test_institution_scoped_admin_sees_only_their_institution_logs(
    api_client: TestClient, db: Session
) -> None:
    inst_a = make_institution(db)
    inst_b = make_institution(db)
    admin_a = make_user(db, roles=[("ADMIN", inst_a.id)])
    admin_b = make_user(db, roles=[("ADMIN", inst_b.id)])

    # Create audit logs in both institutions.
    audit.record(
        db,
        action="inst_a.action",
        actor_user_id=admin_a.id,
        institution_id=inst_a.id,
        meta=None,
    )
    audit.record(
        db,
        action="inst_b.action",
        actor_user_id=admin_b.id,
        institution_id=inst_b.id,
        meta=None,
    )
    db.commit()

    # Admin A sees only their institution's logs.
    response = api_client.get("/api/v1/admin/audit-logs", headers=auth_headers(admin_a))
    assert response.status_code == 200
    actions = [log["action"] for log in response.json()["data"]["items"]]
    assert "inst_a.action" in actions
    assert "inst_b.action" not in actions


def test_platform_admin_sees_all_audit_logs(api_client: TestClient, db: Session) -> None:
    inst_a = make_institution(db)
    inst_b = make_institution(db)
    platform_admin = make_user(db, roles=[("ADMIN", None)])

    audit.record(
        db,
        action="a.action",
        actor_user_id=platform_admin.id,
        institution_id=inst_a.id,
        meta=None,
    )
    audit.record(
        db,
        action="b.action",
        actor_user_id=platform_admin.id,
        institution_id=inst_b.id,
        meta=None,
    )
    db.commit()

    response = api_client.get("/api/v1/admin/audit-logs", headers=auth_headers(platform_admin))
    assert response.status_code == 200
    actions = [log["action"] for log in response.json()["data"]["items"]]
    assert "a.action" in actions
    assert "b.action" in actions


def test_audit_log_filter_by_action(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    admin = make_user(db, roles=[("ADMIN", None)])

    audit.record(
        db,
        action="user.suspended",
        actor_user_id=admin.id,
        institution_id=institution.id,
        meta=None,
    )
    audit.record(
        db,
        action="auth.login",
        actor_user_id=admin.id,
        institution_id=institution.id,
        meta=None,
    )
    db.commit()

    response = api_client.get(
        "/api/v1/admin/audit-logs?action=suspended", headers=auth_headers(admin)
    )
    assert response.status_code == 200
    actions = [log["action"] for log in response.json()["data"]["items"]]
    assert all("suspended" in a for a in actions)


def test_audit_log_filter_by_actor(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    admin = make_user(db, roles=[("ADMIN", None)])
    other = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])

    audit.record(
        db,
        action="admin.action",
        actor_user_id=admin.id,
        institution_id=institution.id,
        meta=None,
    )
    audit.record(
        db,
        action="other.action",
        actor_user_id=other.id,
        institution_id=institution.id,
        meta=None,
    )
    db.commit()

    response = api_client.get(
        f"/api/v1/admin/audit-logs?actor_user_id={admin.id}", headers=auth_headers(admin)
    )
    assert response.status_code == 200
    actors = {log["actor_user_id"] for log in response.json()["data"]["items"]}
    assert str(admin.id) in actors
    assert str(other.id) not in actors
