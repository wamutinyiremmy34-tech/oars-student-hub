"""Institution scoping for operations that act on another user."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.modules.rbac.models import UserRole
from app.modules.rbac.principal import Principal
from app.modules.users.models import StudentProfile, User


def user_institution_ids(db: Session, user_id: uuid.UUID) -> tuple[set[uuid.UUID], bool]:
    """Institutions a user belongs to (profile or scoped role) and whether they hold a platform-wide role."""
    profile_institution = db.scalar(
        select(StudentProfile.institution_id).where(StudentProfile.user_id == user_id)
    )
    role_scopes = db.execute(select(UserRole.institution_id).where(UserRole.user_id == user_id))
    scopes = list(role_scopes.scalars())
    institutions = {i for i in scopes if i is not None}
    if profile_institution is not None:
        institutions.add(profile_institution)
    has_platform_role = any(i is None for i in scopes)
    return institutions, has_platform_role


def authorize_over_user(
    db: Session, principal: Principal, target_id: uuid.UUID, permission: str
) -> User:
    """Return the target user if the principal holds `permission` over them, else raise NotFoundError.

    NotFound (not Forbidden) so that another institution's users cannot be discovered by probing ids.
    A target with a platform-wide role can only be acted on by platform-wide holders, so an
    institution admin can never act on a platform administrator.
    """
    target = db.get(User, target_id)
    if target is None:
        raise NotFoundError("User not found.")
    if principal.can(permission, None):
        return target
    institutions, has_platform_role = user_institution_ids(db, target.id)
    if has_platform_role:
        raise NotFoundError("User not found.")
    if any(principal.can(permission, institution) for institution in institutions):
        return target
    raise NotFoundError("User not found.")
