import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.http import RequestMetaDep
from app.core.responses import Envelope, ok
from app.modules.auth.deps import require_permission
from app.modules.institutions import service
from app.modules.institutions.models import Institution
from app.modules.institutions.schemas import InstitutionIn, InstitutionPatch, InstitutionPublic
from app.modules.rbac.principal import Principal

router = APIRouter(prefix="/institutions", tags=["institutions"])


def _public(i: Institution) -> InstitutionPublic:
    return InstitutionPublic(id=i.id, name=i.name, code=i.code, slug=i.slug)


@router.get(
    "", response_model=Envelope[list[InstitutionPublic]], summary="Active institutions (public)"
)
def list_institutions(db: DbSession) -> Envelope[list[InstitutionPublic]]:
    """Public on purpose: the registration form needs it before the user has an account."""
    rows = db.scalars(
        select(Institution).where(Institution.is_active.is_(True)).order_by(Institution.name)
    )
    return ok([_public(i) for i in rows])


@router.get("/{institution_id}", response_model=Envelope[InstitutionPublic])
def get_institution(institution_id: uuid.UUID, db: DbSession) -> Envelope[InstitutionPublic]:
    return ok(_public(service.get_public(db, institution_id)))


@router.post("", status_code=201, response_model=Envelope[InstitutionPublic])
def create_institution(
    body: InstitutionIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("institution:manage"))],
) -> Envelope[InstitutionPublic]:
    return ok(_public(service.create_institution(db, principal, body, meta)))


@router.patch("/{institution_id}", response_model=Envelope[InstitutionPublic])
def update_institution(
    institution_id: uuid.UUID,
    body: InstitutionPatch,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("institution:update"))],
) -> Envelope[InstitutionPublic]:
    return ok(_public(service.update_institution(db, principal, institution_id, body, meta)))
