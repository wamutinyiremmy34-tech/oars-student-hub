import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.http import RequestMeta
from app.modules.audit import service as audit
from app.modules.institutions.models import Institution
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.rbac.principal import Grant, Principal
from app.modules.rbac.scope import authorize_over_user


def load_grants(db: Session, user_id: uuid.UUID) -> frozenset[Grant]:
    """All (permission, institution) pairs a user holds.

    Platform-only permissions are ignored for institution-scoped assignments, so an institution
    admin never gains platform-level powers through a scoped ADMIN role.
    """
    stmt = (
        select(Permission.code, UserRole.institution_id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .where((UserRole.institution_id.is_(None)) | (Permission.platform_only.is_(False)))
    )
    return frozenset((code, institution_id) for code, institution_id in db.execute(stmt).all())


def get_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is None:
        raise NotFoundError("Role not found.", code="role_not_found")
    return role


def add_user_role(
    db: Session,
    *,
    user_id: uuid.UUID,
    role: Role,
    institution_id: uuid.UUID | None,
    granted_by: uuid.UUID | None,
) -> UserRole:
    """Insert a role assignment WITHOUT authorization. Use grant_role() for caller-initiated grants."""
    existing = db.scalar(
        select(UserRole.id).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
            UserRole.institution_id.is_(None)
            if institution_id is None
            else UserRole.institution_id == institution_id,
        )
    )
    if existing is not None:
        raise ConflictError("The user already holds this role.", code="role_already_assigned")
    assignment = UserRole(
        user_id=user_id,
        role_id=role.id,
        institution_id=institution_id,
        granted_by_user_id=granted_by,
    )
    db.add(assignment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "The user already holds this role.", code="role_already_assigned"
        ) from exc
    return assignment


def _authorize_role_change(
    db: Session, actor: Principal, target_id: uuid.UUID, institution_id: uuid.UUID | None
) -> None:
    # 1) The actor must have authority over the target user (else 404 - no existence leak).
    authorize_over_user(db, actor, target_id, "role:assign")
    # 2) The actor must hold role:assign for the scope being granted. A platform-wide grant
    #    (institution_id None) therefore requires a platform-wide role:assign.
    actor.require("role:assign", institution_id)
    if institution_id is not None and db.get(Institution, institution_id) is None:
        raise BadRequestError("Unknown institution.", code="invalid_institution")


def grant_role(
    db: Session,
    *,
    actor: Principal,
    target_id: uuid.UUID,
    role_name: str,
    institution_id: uuid.UUID | None,
    meta: RequestMeta,
) -> UserRole:
    _authorize_role_change(db, actor, target_id, institution_id)
    role = get_role(db, role_name)
    assignment = add_user_role(
        db, user_id=target_id, role=role, institution_id=institution_id, granted_by=actor.user.id
    )
    audit.record(
        db,
        action="role.granted",
        actor_user_id=actor.user.id,
        target_type="user",
        target_id=str(target_id),
        institution_id=institution_id,
        details={"role": role_name},
        meta=meta,
    )
    db.commit()
    return assignment


def revoke_role(
    db: Session,
    *,
    actor: Principal,
    target_id: uuid.UUID,
    role_name: str,
    institution_id: uuid.UUID | None,
    meta: RequestMeta,
) -> None:
    _authorize_role_change(db, actor, target_id, institution_id)
    role = get_role(db, role_name)
    assignment = db.scalar(
        select(UserRole).where(
            UserRole.user_id == target_id,
            UserRole.role_id == role.id,
            UserRole.institution_id.is_(None)
            if institution_id is None
            else UserRole.institution_id == institution_id,
        )
    )
    if assignment is None:
        raise NotFoundError("The user does not hold this role.", code="role_not_assigned")
    db.delete(assignment)
    audit.record(
        db,
        action="role.revoked",
        actor_user_id=actor.user.id,
        target_type="user",
        target_id=str(target_id),
        institution_id=institution_id,
        details={"role": role_name},
        meta=meta,
    )
    db.commit()
