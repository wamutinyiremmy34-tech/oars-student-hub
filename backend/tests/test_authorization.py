"""Permission, institution-scope, object-level and privilege-escalation tests (real PostgreSQL)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from helpers import auth_headers, make_institution, make_user
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User

pytestmark = pytest.mark.integration


class World:
    """Two institutions, a student in each, a scoped admin for A, and a platform admin."""

    def __init__(self, db: Session) -> None:
        self.inst_a = make_institution(db)
        self.inst_b = make_institution(db)
        self.student_a = make_user(db, institution=self.inst_a, roles=[("STUDENT", self.inst_a.id)])
        self.student_b = make_user(db, institution=self.inst_b, roles=[("STUDENT", self.inst_b.id)])
        self.admin_a = make_user(db, roles=[("ADMIN", self.inst_a.id)])
        self.platform_admin = make_user(db, roles=[("ADMIN", None)])


@pytest.fixture
def world(db: Session) -> World:
    return World(db)


def get_user(client: TestClient, actor: User, target: User):  # type: ignore[no-untyped-def]
    return client.get(f"/api/v1/users/{target.id}", headers=auth_headers(actor))


def suspend(client: TestClient, actor: User, target: User):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/users/{target.id}/suspend", json={"reason": "policy"}, headers=auth_headers(actor)
    )


# --------------------------------------------------------------------------- authentication gate


def test_protected_routes_require_authentication(api_client: TestClient, world: World) -> None:
    target = f"/api/v1/users/{world.student_a.id}"
    assert api_client.get(target).status_code == 401
    assert api_client.post(f"{target}/suspend", json={"reason": "x" * 5}).status_code == 401
    assert api_client.get(target, headers={"Authorization": "Bearer nope"}).status_code == 401


# --------------------------------------------------------------------------- permission checks


def test_user_without_the_permission_is_forbidden(api_client: TestClient, world: World) -> None:
    # A student holds no user:read / user:suspend in any scope.
    for response in (
        get_user(api_client, world.student_a, world.student_b),
        get_user(api_client, world.student_a, world.student_a),
        suspend(api_client, world.student_a, world.student_b),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"


def test_authorization_is_by_permission_not_by_role_name(
    api_client: TestClient, db: Session
) -> None:
    """A role that lacks user:read cannot read users even though it is a 'staff' role."""
    inst = make_institution(db)
    operator = make_user(db, roles=[("PRINTING_OPERATOR", inst.id)])
    student = make_user(db, institution=inst)
    assert get_user(api_client, operator, student).status_code == 403


# --------------------------------------------------------------------------- institution scope


def test_scoped_admin_can_manage_their_own_institution(
    api_client: TestClient, db: Session, world: World
) -> None:
    assert get_user(api_client, world.admin_a, world.student_a).status_code == 200

    response = suspend(api_client, world.admin_a, world.student_a)
    assert response.status_code == 200
    assert response.json()["data"]["user"]["status"] == "SUSPENDED"

    entry = db.scalar(select(AuditLog).where(AuditLog.action == "user.suspended"))
    assert entry is not None
    assert entry.actor_user_id == world.admin_a.id
    assert entry.target_id == str(world.student_a.id)
    assert entry.details == {"reason": "policy"}


def test_scoped_admin_cannot_read_or_modify_another_institution(
    api_client: TestClient, db: Session, world: World
) -> None:
    read = get_user(api_client, world.admin_a, world.student_b)
    write = suspend(api_client, world.admin_a, world.student_b)
    missing = api_client.get(f"/api/v1/users/{uuid.uuid4()}", headers=auth_headers(world.admin_a))

    # 404, not 403, and indistinguishable from a user that truly does not exist (no id probing).
    assert read.status_code == write.status_code == missing.status_code == 404
    assert read.json()["error"]["code"] == missing.json()["error"]["code"] == "not_found"

    db.refresh(world.student_b)
    assert world.student_b.status == "ACTIVE"


def test_platform_admin_can_manage_any_institution(api_client: TestClient, world: World) -> None:
    assert get_user(api_client, world.platform_admin, world.student_a).status_code == 200
    assert get_user(api_client, world.platform_admin, world.student_b).status_code == 200
    assert suspend(api_client, world.platform_admin, world.student_b).status_code == 200


def test_scoped_admin_cannot_act_on_a_platform_admin(api_client: TestClient, world: World) -> None:
    assert get_user(api_client, world.admin_a, world.platform_admin).status_code == 404
    assert suspend(api_client, world.admin_a, world.platform_admin).status_code == 404


def test_scoped_admin_does_not_gain_platform_only_permissions(
    api_client: TestClient, world: World
) -> None:
    def permissions(user: User) -> set[tuple[str, str | None]]:
        data = api_client.get("/api/v1/me", headers=auth_headers(user)).json()["data"]
        return {(p["permission"], p["institution_id"]) for p in data["permissions"]}

    scoped = permissions(world.admin_a)
    assert ("user:suspend", str(world.inst_a.id)) in scoped
    assert not any(
        code in {"institution:manage", "role:manage", "settings:manage"} for code, _ in scoped
    )
    assert not any(inst is None for _, inst in scoped)

    platform = permissions(world.platform_admin)
    assert ("institution:manage", None) in platform
    assert ("settings:manage", None) in platform


def test_admin_cannot_suspend_themselves(api_client: TestClient, world: World) -> None:
    response = suspend(api_client, world.platform_admin, world.platform_admin)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "cannot_suspend_self"


def test_reinstate_restores_access(api_client: TestClient, world: World) -> None:
    suspend(api_client, world.admin_a, world.student_a)
    assert api_client.get("/api/v1/me", headers=auth_headers(world.student_a)).status_code == 401
    response = api_client.post(
        f"/api/v1/users/{world.student_a.id}/reinstate", headers=auth_headers(world.admin_a)
    )
    assert response.status_code == 200
    assert api_client.get("/api/v1/me", headers=auth_headers(world.student_a)).status_code == 200
    assert suspend(api_client, world.admin_a, world.student_b).status_code == 404


# --------------------------------------------------------------------------- object ownership


def test_me_always_returns_the_callers_own_data(api_client: TestClient, world: World) -> None:
    for user in (world.student_a, world.student_b):
        data = api_client.get("/api/v1/me", headers=auth_headers(user)).json()["data"]
        assert data["user"]["id"] == str(user.id)  # there is no id parameter to tamper with


# --------------------------------------------------------------------------- role grants / escalation


def role_names(db: Session, user: User) -> set[tuple[str, uuid.UUID | None]]:
    rows = db.execute(
        select(Role.name, UserRole.institution_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    return {(name, inst) for name, inst in rows}


def grant(
    client: TestClient, actor: User, target: User, role: str, institution_id: uuid.UUID | None
):  # type: ignore[no-untyped-def]
    body: dict[str, object] = {"role": role}
    if institution_id is not None:
        body["institution_id"] = str(institution_id)
    return client.post(f"/api/v1/users/{target.id}/roles", json=body, headers=auth_headers(actor))


def test_scoped_admin_can_grant_scoped_roles_in_their_institution(
    api_client: TestClient, db: Session, world: World
) -> None:
    response = grant(
        api_client, world.admin_a, world.student_a, "PRINTING_OPERATOR", world.inst_a.id
    )
    assert response.status_code == 201
    assert ("PRINTING_OPERATOR", world.inst_a.id) in role_names(db, world.student_a)
    assert db.scalar(select(AuditLog).where(AuditLog.action == "role.granted")) is not None

    assert (
        grant(
            api_client, world.admin_a, world.student_a, "PRINTING_OPERATOR", world.inst_a.id
        ).status_code
        == 409
    )


def test_scoped_admin_cannot_escalate_to_platform_wide_or_other_institutions(
    api_client: TestClient, db: Session, world: World
) -> None:
    platform_wide = grant(api_client, world.admin_a, world.student_a, "ADMIN", None)
    other_institution = grant(api_client, world.admin_a, world.student_a, "ADMIN", world.inst_b.id)
    other_user = grant(
        api_client, world.admin_a, world.student_b, "PRINTING_OPERATOR", world.inst_a.id
    )

    assert platform_wide.status_code == 403
    assert other_institution.status_code == 403
    assert other_user.status_code == 404  # target is outside the actor's institution
    assert role_names(db, world.student_a) == {("STUDENT", world.inst_a.id)}


def test_non_admin_cannot_grant_roles(api_client: TestClient, world: World) -> None:
    response = grant(api_client, world.student_a, world.student_a, "ADMIN", None)
    assert response.status_code == 403


def test_platform_admin_can_grant_and_revoke_platform_wide_roles(
    api_client: TestClient, db: Session, world: World
) -> None:
    created = grant(api_client, world.platform_admin, world.student_a, "ADMIN", None)
    assert created.status_code == 201
    assert ("ADMIN", None) in role_names(db, world.student_a)

    revoked = api_client.delete(
        f"/api/v1/users/{world.student_a.id}/roles/ADMIN",
        headers=auth_headers(world.platform_admin),
    )
    assert revoked.status_code == 200
    assert ("ADMIN", None) not in role_names(db, world.student_a)
    assert db.scalar(select(AuditLog).where(AuditLog.action == "role.revoked")) is not None

    again = api_client.delete(
        f"/api/v1/users/{world.student_a.id}/roles/ADMIN",
        headers=auth_headers(world.platform_admin),
    )
    assert again.status_code == 404


def test_scoped_admin_cannot_revoke_a_platform_wide_role(
    api_client: TestClient, world: World
) -> None:
    response = api_client.delete(
        f"/api/v1/users/{world.platform_admin.id}/roles/ADMIN", headers=auth_headers(world.admin_a)
    )
    assert response.status_code == 404


def test_role_changes_take_effect_on_the_next_request(
    api_client: TestClient, db: Session, world: World
) -> None:
    assert get_user(api_client, world.student_a, world.student_b).status_code == 403
    grant(api_client, world.platform_admin, world.student_a, "ADMIN", None)
    assert get_user(api_client, world.student_a, world.student_b).status_code == 200
