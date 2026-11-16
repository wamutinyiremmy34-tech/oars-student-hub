"""The authenticated caller and the permission/scope rules.

Scope semantics:
  * A grant with institution_id None is platform-wide and satisfies any target.
  * A grant with an institution_id only satisfies a target in that same institution.
  * A platform-level operation (target institution None) is satisfied only by platform-wide grants.
"""

import uuid
from dataclasses import dataclass

from app.core.errors import ForbiddenError, NotFoundError
from app.modules.users.models import User

Grant = tuple[str, uuid.UUID | None]


@dataclass(frozen=True)
class PermissionScope:
    platform_wide: bool
    institution_ids: frozenset[uuid.UUID]


@dataclass(frozen=True)
class Principal:
    user: User
    grants: frozenset[Grant]

    def can(self, permission: str, institution_id: uuid.UUID | None = None) -> bool:
        for code, scope in self.grants:
            if code != permission:
                continue
            if scope is None:
                return True
            if institution_id is not None and scope == institution_id:
                return True
        return False

    def has_any_scope(self, permission: str) -> bool:
        return any(code == permission for code, _ in self.grants)

    def require(self, permission: str, institution_id: uuid.UUID | None = None) -> None:
        if not self.can(permission, institution_id):
            raise ForbiddenError()

    def scope_for(self, permission: str) -> PermissionScope:
        platform_wide = False
        institutions: set[uuid.UUID] = set()
        for code, scope in self.grants:
            if code != permission:
                continue
            if scope is None:
                platform_wide = True
            else:
                institutions.add(scope)
        return PermissionScope(platform_wide, frozenset(institutions))

    def ensure_access(
        self,
        *,
        owner_id: uuid.UUID,
        permission: str,
        institution_id: uuid.UUID | None = None,
    ) -> None:
        """Object-level check: the owner, or a holder of `permission` in scope. Otherwise 404 (no IDOR leak)."""
        if self.user.id == owner_id or self.can(permission, institution_id):
            return
        raise NotFoundError()
