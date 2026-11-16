"""The permission and role catalog: the single source of truth for what the platform can authorize.

The initial catalog is inserted by migration 0001 as a frozen snapshot. Later changes ship as new
migrations, and tests/test_database_constraints.py fails if this file and the database drift apart.

Authorization code checks PERMISSIONS, never role names.
"""

from dataclasses import dataclass

ALL = "*"


@dataclass(frozen=True)
class PermissionDef:
    code: str
    description: str
    platform_only: bool = False


PERMISSIONS: tuple[PermissionDef, ...] = (
    PermissionDef("user:read", "Read user accounts"),
    PermissionDef("user:update", "Update user accounts"),
    PermissionDef("user:suspend", "Suspend and reinstate user accounts"),
    PermissionDef("role:assign", "Grant and revoke roles"),
    PermissionDef("role:manage", "Manage role and permission definitions", platform_only=True),
    PermissionDef("institution:read", "Read institutions"),
    PermissionDef("institution:update", "Update institution details"),
    PermissionDef("institution:manage", "Create and deactivate institutions", platform_only=True),
    PermissionDef("resource:create", "Create resources"),
    PermissionDef("resource:update", "Update own resources"),
    PermissionDef("resource:submit", "Submit resources for review"),
    PermissionDef("resource:review", "Review and moderate resources"),
    PermissionDef("resource:publish", "Publish and archive resources"),
    PermissionDef("resource:delete", "Delete own resources"),
    PermissionDef("resource:manage_any", "Manage any resource within scope"),
    PermissionDef("order:create", "Create printing orders"),
    PermissionDef("order:read", "Read own orders"),
    PermissionDef("order:read_any", "Read any order within scope"),
    PermissionDef("order:update_status", "Update printing order status"),
    PermissionDef("payment:read", "Read payments"),
    PermissionDef("payment:manage", "Administer payments"),
    PermissionDef("advertisement:manage", "Manage advertisements and campaigns"),
    PermissionDef("analytics:read", "View analytics"),
    PermissionDef("audit:read", "Read audit logs"),
    PermissionDef("notification:read", "Read own notifications"),
    PermissionDef("settings:manage", "Manage platform settings", platform_only=True),
    # Added in migration 0002 (academic structure, resources, premium access)
    PermissionDef(
        "resource:review_own",
        "Review or publish one's own resources (separation-of-duties override)",
    ),
    PermissionDef("catalog:manage", "Manage faculties, departments, programs and courses"),
    PermissionDef("category:manage", "Manage resource categories", platform_only=True),
    PermissionDef("entitlement:manage", "Grant and revoke access to premium resources"),
    # Added in migration 0003 (printing and payments)
    PermissionDef("payment:create", "Pay for orders and premium resources online"),
    PermissionDef("payment:record_cash", "Record cash received at pickup"),
    PermissionDef("printshop:manage", "Manage print shops, their staff and pricing"),
    PermissionDef(
        "order:manage_any", "Act on any print order in the institution, and set retention holds"
    ),
)

# role name -> (description, permission codes). ALL means every permission.
ROLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "STUDENT": (
        "University student",
        ("institution:read", "order:create", "order:read", "payment:create", "notification:read"),
    ),
    "RESOURCE_PROVIDER": (
        "Uploads and manages academic resources",
        (
            "resource:create",
            "resource:update",
            "resource:submit",
            "resource:delete",
            "notification:read",
        ),
    ),
    "PRINTING_OPERATOR": (
        "Processes printing orders for a print shop",
        (
            "institution:read",
            "order:read_any",
            "order:update_status",
            "payment:record_cash",
            "notification:read",
        ),
    ),
    "ADMIN": ("Administrator (platform-wide or institution-scoped)", (ALL,)),
}


# Held by NO default role. It exists so a deliberately-created role can be allowed to moderate its own
# resources (separation of duties); ADMIN must not get it implicitly.
NOT_IN_ADMIN = frozenset({"resource:review_own"})


def permissions_for_role(role_name: str) -> frozenset[str]:
    _, codes = ROLES[role_name]
    if codes == (ALL,):
        return frozenset(p.code for p in PERMISSIONS) - NOT_IN_ADMIN
    return frozenset(codes)
