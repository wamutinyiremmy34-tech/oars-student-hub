import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError
from app.core.http import RequestMeta
from app.core.security import hash_password
from app.modules.audit import service as audit
from app.modules.auth.service import revoke_all_for_user
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.principal import Principal
from app.modules.rbac.scope import authorize_over_user, user_institution_ids
from app.modules.rbac.service import add_user_role, get_role
from app.modules.users.models import User, UserStatus
from app.modules.users.schemas import (
    GrantOut,
    MeOut,
    RoleAssignmentOut,
    StudentProfileOut,
    UserAdminOut,
    UserPublic,
)


def _role_assignments(db: Session, user_id: uuid.UUID) -> list[RoleAssignmentOut]:
    rows = db.execute(
        select(Role.name, UserRole.institution_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.name)
    )
    return [RoleAssignmentOut(role=name, institution_id=inst) for name, inst in rows]


def build_me(db: Session, principal: Principal) -> MeOut:
    user = principal.user
    profile = user.student_profile
    grants = sorted(principal.grants, key=lambda g: (g[0], str(g[1])))
    return MeOut(
        user=UserPublic.from_user(user),
        student_profile=StudentProfileOut.from_profile(profile) if profile else None,
        roles=_role_assignments(db, user.id),
        permissions=[GrantOut(permission=code, institution_id=inst) for code, inst in grants],
    )


def _admin_view(db: Session, user: User) -> UserAdminOut:
    institutions, _ = user_institution_ids(db, user.id)
    return UserAdminOut(
        user=UserPublic.from_user(user),
        suspended_at=user.suspended_at,
        suspended_reason=user.suspended_reason,
        institution_ids=sorted(institutions, key=str),
        roles=_role_assignments(db, user.id),
    )


def get_user_for_admin(db: Session, principal: Principal, user_id: uuid.UUID) -> UserAdminOut:
    return _admin_view(db, authorize_over_user(db, principal, user_id, "user:read"))


def update_me(
    db: Session, *, principal: Principal, full_name: str | None, phone: str | None, meta: RequestMeta
) -> MeOut:
    """Let a user update their own display name and phone number."""
    user = principal.user
    changed: list[str] = []
    if full_name is not None:
        user.full_name = full_name.strip()
        changed.append("full_name")
    if phone is not None:
        # Empty string clears the phone number
        user.phone = phone.strip() or None
        changed.append("phone")
    if changed:
        audit.record(
            db,
            action="user.profile_updated",
            actor_user_id=user.id,
            target_type="user",
            target_id=str(user.id),
            details={"changed": changed},
            meta=meta,
        )
        db.commit()
    return build_me(db, principal)


def suspend_user(
    db: Session, *, principal: Principal, user_id: uuid.UUID, reason: str, meta: RequestMeta
) -> UserAdminOut:
    if user_id == principal.user.id:
        raise BadRequestError("You cannot suspend your own account.", code="cannot_suspend_self")
    target = authorize_over_user(db, principal, user_id, "user:suspend")
    if target.status == UserStatus.SUSPENDED:
        raise ConflictError("This account is already suspended.", code="already_suspended")
    target.status = UserStatus.SUSPENDED
    target.suspended_at = datetime.now(UTC)
    target.suspended_reason = reason
    # Existing access tokens stop working immediately (the user is re-read per request);
    # revoking refresh tokens stops new access tokens from being minted.
    revoke_all_for_user(db, target.id, reason="suspended")
    audit.record(
        db,
        action="user.suspended",
        actor_user_id=principal.user.id,
        target_type="user",
        target_id=str(target.id),
        details={"reason": reason},
        meta=meta,
    )
    db.commit()
    return _admin_view(db, target)


def reinstate_user(
    db: Session, *, principal: Principal, user_id: uuid.UUID, meta: RequestMeta
) -> UserAdminOut:
    target = authorize_over_user(db, principal, user_id, "user:suspend")
    if target.status != UserStatus.SUSPENDED:
        raise ConflictError("This account is not suspended.", code="not_suspended")
    target.status = UserStatus.ACTIVE
    target.suspended_at = None
    target.suspended_reason = None
    audit.record(
        db,
        action="user.reinstated",
        actor_user_id=principal.user.id,
        target_type="user",
        target_id=str(target.id),
        meta=meta,
    )
    db.commit()
    return _admin_view(db, target)


def create_platform_admin(db: Session, *, email: str, password: str, full_name: str) -> User:
    """Bootstrap the first platform administrator (used by the CLI; there is no public endpoint)."""
    user = User(
        email=email.strip().lower(),
        full_name=full_name,
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE,
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    add_user_role(
        db, user_id=user.id, role=get_role(db, "ADMIN"), institution_id=None, granted_by=None
    )
    audit.record(
        db,
        action="user.platform_admin_created",
        target_type="user",
        target_id=str(user.id),
        details={"via": "cli"},
    )
    db.commit()
    return user
