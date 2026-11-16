"""Pure unit tests of the permission/scope rules (no database)."""

import uuid
from types import SimpleNamespace

import pytest

from app.core.errors import ForbiddenError, NotFoundError
from app.modules.rbac.catalog import PERMISSIONS, ROLES, permissions_for_role
from app.modules.rbac.principal import Principal

INST_A, INST_B = uuid.uuid4(), uuid.uuid4()


def principal(*grants: tuple[str, uuid.UUID | None]) -> Principal:
    return Principal(user=SimpleNamespace(id=uuid.uuid4()), grants=frozenset(grants))  # type: ignore[arg-type]


def test_platform_wide_grant_satisfies_any_institution_and_platform_level() -> None:
    p = principal(("user:suspend", None))
    assert p.can("user:suspend", INST_A)
    assert p.can("user:suspend", INST_B)
    assert p.can("user:suspend", None)


def test_scoped_grant_only_satisfies_its_own_institution() -> None:
    p = principal(("user:suspend", INST_A))
    assert p.can("user:suspend", INST_A)
    assert not p.can("user:suspend", INST_B)


def test_scoped_grant_never_satisfies_platform_level_operations() -> None:
    assert not principal(("user:suspend", INST_A)).can("user:suspend", None)


def test_missing_permission_is_denied() -> None:
    assert not principal(("user:read", None)).can("user:suspend", INST_A)


def test_has_any_scope_and_scope_for() -> None:
    p = principal(("user:read", INST_A), ("user:read", INST_B), ("audit:read", None))
    assert p.has_any_scope("user:read")
    assert not p.has_any_scope("user:suspend")
    scope = p.scope_for("user:read")
    assert scope.platform_wide is False
    assert scope.institution_ids == {INST_A, INST_B}
    assert p.scope_for("audit:read").platform_wide is True


def test_require_raises_forbidden() -> None:
    with pytest.raises(ForbiddenError):
        principal().require("user:read", INST_A)
    principal(("user:read", INST_A)).require("user:read", INST_A)


def test_ensure_access_allows_owner_or_scoped_holder_else_not_found() -> None:
    owner = principal()
    owner.ensure_access(owner_id=owner.user.id, permission="order:read_any", institution_id=INST_A)

    operator = principal(("order:read_any", INST_A))
    operator.ensure_access(
        owner_id=uuid.uuid4(), permission="order:read_any", institution_id=INST_A
    )

    with pytest.raises(
        NotFoundError
    ):  # IDOR: not-owner, no permission -> looks like it doesn't exist
        principal().ensure_access(
            owner_id=uuid.uuid4(), permission="order:read_any", institution_id=INST_A
        )
    with pytest.raises(NotFoundError):  # permission held, but for another institution
        operator.ensure_access(
            owner_id=uuid.uuid4(), permission="order:read_any", institution_id=INST_B
        )


def test_catalog_is_internally_consistent() -> None:
    codes = [p.code for p in PERMISSIONS]
    assert len(codes) == len(set(codes))
    assert set(ROLES) == {"STUDENT", "RESOURCE_PROVIDER", "PRINTING_OPERATOR", "ADMIN"}
    for name in ROLES:
        assert permissions_for_role(name) <= set(codes)
    assert permissions_for_role("ADMIN") == set(codes) - {"resource:review_own"}


def test_only_admin_holds_platform_only_permissions() -> None:
    platform_only = {p.code for p in PERMISSIONS if p.platform_only}
    assert {"institution:manage", "role:manage", "settings:manage"} <= platform_only
    for name in ("STUDENT", "RESOURCE_PROVIDER", "PRINTING_OPERATOR"):
        assert not (permissions_for_role(name) & platform_only)


def test_the_catalog_contains_the_required_permissions() -> None:
    codes = {p.code for p in PERMISSIONS}
    required = {
        "user:read", "user:update", "user:suspend", "institution:read", "institution:manage",
        "resource:create", "resource:update", "resource:submit", "resource:review",
        "resource:publish", "resource:delete", "order:create", "order:read",
        "order:update_status", "payment:read", "payment:manage", "advertisement:manage",
        "analytics:read", "audit:read",
    }  # fmt: skip
    assert required <= codes
