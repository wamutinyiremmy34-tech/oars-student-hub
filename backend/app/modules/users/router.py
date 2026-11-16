import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import StringConstraints

from app.core.deps import DbSession
from app.core.http import RequestMetaDep
from app.core.responses import Envelope, ok
from app.modules.auth.deps import CurrentPrincipal, require_permission
from app.modules.auth.schemas import MessageOut
from app.modules.rbac import service as rbac_service
from app.modules.rbac.principal import Principal
from app.modules.users import service
from app.modules.users.schemas import (
    GrantRoleIn,
    MeOut,
    RoleAssignmentOut,
    SuspendIn,
    UserAdminOut,
)

me_router = APIRouter(tags=["users"])
users_router = APIRouter(prefix="/users", tags=["users"])

RoleName = Annotated[str, StringConstraints(pattern=r"^[A-Z_]{3,50}$")]


@me_router.get("/me", response_model=Envelope[MeOut], summary="The authenticated user")
def get_me(principal: CurrentPrincipal, db: DbSession) -> Envelope[MeOut]:
    # Object-level security by construction: there is no id parameter to tamper with.
    return ok(service.build_me(db, principal))


@users_router.get("/{user_id}", response_model=Envelope[UserAdminOut])
def get_user(
    user_id: uuid.UUID,
    db: DbSession,
    principal: Annotated[Principal, Depends(require_permission("user:read"))],
) -> Envelope[UserAdminOut]:
    return ok(service.get_user_for_admin(db, principal, user_id))


@users_router.post("/{user_id}/suspend", response_model=Envelope[UserAdminOut])
def suspend_user(
    user_id: uuid.UUID,
    body: SuspendIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("user:suspend"))],
) -> Envelope[UserAdminOut]:
    return ok(
        service.suspend_user(
            db, principal=principal, user_id=user_id, reason=body.reason, meta=meta
        )
    )


@users_router.post("/{user_id}/reinstate", response_model=Envelope[UserAdminOut])
def reinstate_user(
    user_id: uuid.UUID,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("user:suspend"))],
) -> Envelope[UserAdminOut]:
    return ok(service.reinstate_user(db, principal=principal, user_id=user_id, meta=meta))


@users_router.post("/{user_id}/roles", status_code=201, response_model=Envelope[RoleAssignmentOut])
def grant_role(
    user_id: uuid.UUID,
    body: GrantRoleIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("role:assign"))],
) -> Envelope[RoleAssignmentOut]:
    assignment = rbac_service.grant_role(
        db,
        actor=principal,
        target_id=user_id,
        role_name=body.role,
        institution_id=body.institution_id,
        meta=meta,
    )
    return ok(RoleAssignmentOut(role=body.role, institution_id=assignment.institution_id))


@users_router.delete("/{user_id}/roles/{role_name}", response_model=Envelope[MessageOut])
def revoke_role(
    user_id: uuid.UUID,
    role_name: RoleName,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("role:assign"))],
    institution_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Envelope[MessageOut]:
    rbac_service.revoke_role(
        db,
        actor=principal,
        target_id=user_id,
        role_name=role_name,
        institution_id=institution_id,
        meta=meta,
    )
    return ok(MessageOut(message="Role revoked."))
