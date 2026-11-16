import re
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.http import RequestMeta
from app.modules.audit import service as audit
from app.modules.institutions.models import Institution
from app.modules.institutions.schemas import InstitutionIn, InstitutionPatch
from app.modules.rbac.principal import Principal


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:100]


def get_public(db: Session, institution_id: uuid.UUID) -> Institution:
    institution = db.get(Institution, institution_id)
    if institution is None or not institution.is_active:
        raise NotFoundError("Institution not found.")
    return institution


def create_institution(
    db: Session, principal: Principal, data: InstitutionIn, meta: RequestMeta
) -> Institution:
    principal.require(
        "institution:manage", None
    )  # platform-only: scoped admins can never add universities
    institution = Institution(name=data.name, code=data.code.upper(), slug=slugify(data.name))
    db.add(institution)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "An institution with that name or code already exists.", code="already_exists"
        ) from exc
    audit.record(
        db, action="institution.created", actor_user_id=principal.user.id, target_type="institution",
        target_id=str(institution.id), institution_id=institution.id, meta=meta,
    )  # fmt: skip
    db.commit()
    return institution


def update_institution(
    db: Session,
    principal: Principal,
    institution_id: uuid.UUID,
    patch: InstitutionPatch,
    meta: RequestMeta,
) -> Institution:
    institution = db.get(Institution, institution_id)
    if institution is None or not principal.can("institution:update", institution_id):
        raise NotFoundError("Institution not found.")
    changes = patch.model_dump(exclude_unset=True)
    if "is_active" in changes:
        principal.require(
            "institution:manage", None
        )  # (de)activating a university is platform-level
    for field, value in changes.items():
        setattr(institution, field, value)
    audit.record(
        db, action="institution.updated", actor_user_id=principal.user.id, target_type="institution",
        target_id=str(institution.id), institution_id=institution.id, meta=meta,
    )  # fmt: skip
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "An institution with that name already exists.", code="already_exists"
        ) from exc
    return institution
