"""Who may see and download what. This is the single place that decides file access."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.http import RequestMeta
from app.core.security import create_download_token
from app.modules.audit import service as audit
from app.modules.files.models import StoredFile
from app.modules.rbac.principal import Principal
from app.modules.resources.models import (
    AccessType,
    Entitlement,
    Resource,
    ResourceDownload,
    ResourceStatus,
    ResourceVersion,
)
from app.modules.resources.schemas import DownloadOut
from app.modules.users.models import User
from app.providers.storage.base import StorageBackend


@dataclass(frozen=True)
class AccessDecision:
    can_download: bool
    reason: str | None
    entitlement_status: str | None = None


def is_owner(principal: Principal | None, resource: Resource) -> bool:
    return principal is not None and resource.provider_id == principal.user.id


def is_reviewer(principal: Principal | None, resource: Resource) -> bool:
    """Staff with moderation or management rights over the resource's institution."""
    return principal is not None and (
        principal.can("resource:review", resource.institution_id)
        or principal.can("resource:manage_any", resource.institution_id)
    )


def visible_to(principal: Principal | None, resource: Resource) -> bool:
    return (
        resource.status == ResourceStatus.PUBLISHED
        or is_owner(principal, resource)
        or is_reviewer(principal, resource)
    )


def active_entitlement(
    db: Session, user_id: uuid.UUID, resource_id: uuid.UUID
) -> Entitlement | None:
    entitlement = db.scalar(
        select(Entitlement).where(
            Entitlement.user_id == user_id, Entitlement.resource_id == resource_id
        )
    )
    if entitlement is None or entitlement.status != "ACTIVE":
        return None
    if entitlement.expires_at is not None and entitlement.expires_at <= datetime.now(UTC):
        return None
    return entitlement


def evaluate_access(db: Session, principal: Principal | None, resource: Resource) -> AccessDecision:
    if principal is None:
        return AccessDecision(False, "authentication_required")
    if is_owner(principal, resource) or is_reviewer(principal, resource):
        return AccessDecision(True, None)  # ownership / admin override, any status
    if resource.status != ResourceStatus.PUBLISHED:
        return AccessDecision(False, "not_available")
    if resource.access_type == AccessType.FREE:
        return AccessDecision(True, None)
    entitlement = active_entitlement(db, principal.user.id, resource.id)
    if entitlement is not None:
        return AccessDecision(True, None, entitlement.status)
    return AccessDecision(False, "premium_required")


def downloadable_version(db: Session, resource: Resource) -> ResourceVersion | None:
    """Published resources serve their explicitly-marked current version; staff/owners previewing a
    non-published resource get the newest version."""
    if resource.status == ResourceStatus.PUBLISHED:
        stmt = select(ResourceVersion).where(
            ResourceVersion.resource_id == resource.id, ResourceVersion.is_current.is_(True)
        )
    else:
        stmt = (
            select(ResourceVersion)
            .where(ResourceVersion.resource_id == resource.id)
            .order_by(ResourceVersion.version_number.desc())
            .limit(1)
        )
    return db.scalar(stmt)


def create_download(
    db: Session,
    *,
    principal: Principal,
    resource_id: uuid.UUID,
    storage: StorageBackend,
    meta: RequestMeta,
) -> DownloadOut:
    # 1) authenticated (dependency)  2) exists  3) visible  4) free/premium/entitlement  5) override
    resource = db.get(Resource, resource_id)
    if resource is None or not visible_to(principal, resource):
        raise NotFoundError(
            "Resource not found."
        )  # unpublished resources do not exist for the public

    decision = evaluate_access(db, principal, resource)
    if not decision.can_download:
        if decision.reason == "premium_required":
            raise ForbiddenError(
                "This is a premium resource. You need access to download it.",
                code="premium_required",
            )
        raise NotFoundError("Resource not found.")

    version = downloadable_version(db, resource)
    stored = db.get(StoredFile, version.file_id) if version else None
    if version is None or stored is None:
        raise NotFoundError("This resource has no file yet.", code="no_file")
    if stored.scan_status == "INFECTED":
        raise ConflictError("This file is unavailable.", code="file_unavailable")

    settings = get_settings()
    ttl = settings.download_url_ttl_seconds
    signed = storage.presigned_get_url(
        stored.storage_key,
        filename=stored.original_filename,
        content_type=stored.mime_type,
        expires_in=ttl,
    )
    delivery = "SIGNED_URL" if signed else "STREAM"
    if signed is None:
        token = create_download_token(
            user_id=str(principal.user.id), file_id=str(stored.id), ttl_seconds=ttl
        )
        signed = f"{settings.api_v1_prefix}/downloads/{token}"

    db.add(
        ResourceDownload(
            resource_id=resource.id,
            version_id=version.id,
            user_id=principal.user.id,
            delivery=delivery,
            ip_address=meta.ip,
        )
    )
    db.commit()
    return DownloadOut(
        url=signed, expires_in=ttl, filename=stored.original_filename, delivery=delivery
    )  # type: ignore[arg-type]


# --------------------------------------------------------------------------- entitlements


def grant_entitlement(
    db: Session,
    *,
    resource: Resource,
    user_id: uuid.UUID,
    source: str,
    reference: str | None,
    expires_at: datetime | None,
    granted_by: uuid.UUID | None,
    meta: RequestMeta | None,
    commit: bool = True,
) -> Entitlement:
    """Create or reactivate the user's entitlement. Payments (a later phase) call this with source PURCHASE."""
    if resource.access_type != AccessType.PREMIUM:
        raise ConflictError("Only premium resources use entitlements.", code="not_premium")
    entitlement = db.scalar(
        select(Entitlement).where(
            Entitlement.user_id == user_id, Entitlement.resource_id == resource.id
        )
    )
    if entitlement is None:
        entitlement = Entitlement(user_id=user_id, resource_id=resource.id, source=source)
        db.add(entitlement)
    entitlement.source = source
    entitlement.source_reference = reference
    entitlement.status = "ACTIVE"
    entitlement.expires_at = expires_at
    entitlement.revoked_at = None
    entitlement.granted_by_user_id = granted_by
    db.flush()
    audit.record(
        db, action="entitlement.granted", actor_user_id=granted_by, target_type="resource",
        target_id=str(resource.id), institution_id=resource.institution_id,
        details={"user_id": str(user_id), "source": source}, meta=meta,
    )  # fmt: skip
    if commit:
        db.commit()
    return entitlement


def grant_entitlement_as_admin(
    db: Session,
    *,
    principal: Principal,
    resource_id: uuid.UUID,
    user_id: uuid.UUID,
    expires_at: datetime | None,
    reference: str | None,
    meta: RequestMeta,
) -> Entitlement:
    resource = db.get(Resource, resource_id)
    if resource is None or not principal.can("entitlement:manage", resource.institution_id):
        raise NotFoundError("Resource not found.")
    if db.get(User, user_id) is None:
        raise NotFoundError("User not found.")
    return grant_entitlement(
        db, resource=resource, user_id=user_id, source="ADMIN_GRANT", reference=reference,
        expires_at=expires_at, granted_by=principal.user.id, meta=meta,
    )  # fmt: skip


def revoke_entitlement(
    db: Session,
    *,
    principal: Principal,
    resource_id: uuid.UUID,
    user_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    resource = db.get(Resource, resource_id)
    if resource is None or not principal.can("entitlement:manage", resource.institution_id):
        raise NotFoundError("Resource not found.")
    entitlement = db.scalar(
        select(Entitlement).where(
            Entitlement.user_id == user_id, Entitlement.resource_id == resource_id
        )
    )
    if entitlement is None or entitlement.status == "REVOKED":
        raise NotFoundError("Entitlement not found.")
    entitlement.status = "REVOKED"
    entitlement.revoked_at = datetime.now(UTC)
    audit.record(
        db, action="entitlement.revoked", actor_user_id=principal.user.id, target_type="resource",
        target_id=str(resource.id), institution_id=resource.institution_id,
        details={"user_id": str(user_id)}, meta=meta,
    )  # fmt: skip
    db.commit()
