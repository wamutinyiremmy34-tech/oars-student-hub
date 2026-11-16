"""Resource CRUD and the moderation lifecycle.

    DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED -> PUBLISHED -> ARCHIVED
                              \\-> REJECTED -> (provider edits) -> DRAFT

Rules enforced here (not in the UI):
  * only the owning provider edits, uploads, submits or deletes their resource;
  * reviewers act only inside the institution scope of their permission;
  * nobody reviews or publishes their own resource unless they hold resource:review_own.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fastapi import UploadFile
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.http import RequestMeta
from app.modules.academic.models import Course
from app.modules.audit import service as audit
from app.modules.files.models import StoredFile
from app.modules.files.service import store_upload
from app.modules.institutions.models import Institution
from app.modules.rbac.principal import Principal
from app.modules.resources import access
from app.modules.resources.models import (
    Bookmark,
    CourseResource,
    Entitlement,
    Resource,
    ResourceCategory,
    ResourceDownload,
    ResourceReview,
    ResourceStatus,
    ResourceTag,
    ResourceVersion,
    Tag,
)
from app.modules.resources.schemas import ResourceCreate, ResourcePatch, StatsOut
from app.providers.scanner import MalwareScanner
from app.providers.storage.base import StorageBackend

S = ResourceStatus
EDITABLE = {S.DRAFT, S.REJECTED}
MAX_VERSIONS = 20
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- lookup and access guards


def get_resource(db: Session, resource_id: uuid.UUID, *, lock: bool = False) -> Resource:
    stmt = select(Resource).where(Resource.id == resource_id)
    if lock:
        stmt = stmt.with_for_update()
    resource = db.scalar(stmt)
    if resource is None:
        raise NotFoundError("Resource not found.")
    return resource


def get_visible_resource(
    db: Session, principal: Principal | None, resource_id: uuid.UUID
) -> Resource:
    resource = get_resource(db, resource_id)
    if not access.visible_to(principal, resource):
        raise NotFoundError(
            "Resource not found."
        )  # drafts and unpublished items do not exist publicly
    return resource


def _deny(principal: Principal, resource: Resource) -> ForbiddenError | NotFoundError:
    """403 when the caller can see the resource anyway, otherwise 404 (do not reveal it exists)."""
    return (
        ForbiddenError()
        if access.visible_to(principal, resource)
        else NotFoundError("Resource not found.")
    )


def _owned(
    db: Session,
    principal: Principal,
    resource_id: uuid.UUID,
    permission: str,
    *,
    lock: bool = False,
) -> Resource:
    resource = get_resource(db, resource_id, lock=lock)
    if resource.provider_id != principal.user.id:
        raise _deny(principal, resource)
    principal.require(permission, resource.institution_id)
    return resource


def _staff(db: Session, principal: Principal, resource_id: uuid.UUID, permission: str) -> Resource:
    resource = get_resource(db, resource_id, lock=True)
    if not principal.can(permission, resource.institution_id):
        raise _deny(principal, resource)
    if resource.provider_id == principal.user.id and not principal.can(
        "resource:review_own", resource.institution_id
    ):
        raise ForbiddenError("You cannot moderate your own resource.", code="cannot_review_own")
    return resource


def _require_status(resource: Resource, allowed: set[str]) -> None:
    if resource.status not in allowed:
        raise ConflictError(
            f"This action is not available while the resource is {resource.status}.",
            code="invalid_transition",
        )


def _record(
    db: Session, principal: Principal, resource: Resource, *, decision: str, to_status: str,
    reason: str | None, meta: RequestMeta, version_id: uuid.UUID | None = None,
) -> None:  # fmt: skip
    from_status = resource.status
    resource.status = to_status
    db.add(
        ResourceReview(
            resource_id=resource.id, version_id=version_id, actor_user_id=principal.user.id,
            decision=decision, from_status=from_status, to_status=to_status, reason=reason,
        )
    )  # fmt: skip
    audit.record(
        db, action=f"resource.{decision.lower()}", actor_user_id=principal.user.id, target_type="resource",
        target_id=str(resource.id), institution_id=resource.institution_id,
        details={"from": from_status, "to": to_status, **({"reason": reason} if reason else {})}, meta=meta,
    )  # fmt: skip


# --------------------------------------------------------------------------- tags / courses


def _resolve_tags(db: Session, names: Sequence[str]) -> list[Tag]:
    unique = sorted({n.strip().lower() for n in names if n.strip()})
    if not unique:
        return []
    db.execute(
        pg_insert(Tag)
        .values([{"name": n} for n in unique])
        .on_conflict_do_nothing(index_elements=["name"])
    )
    return list(db.scalars(select(Tag).where(Tag.name.in_(unique))))


def _resolve_courses(
    db: Session, institution_id: uuid.UUID, course_ids: Sequence[uuid.UUID]
) -> list[uuid.UUID]:
    unique = list(dict.fromkeys(course_ids))
    if not unique:
        return []
    found = set(
        db.scalars(
            select(Course.id).where(
                Course.id.in_(unique),
                Course.institution_id == institution_id,
                Course.is_active.is_(True),
            )
        )
    )
    if found != set(unique):
        raise BadRequestError(
            "One or more courses do not belong to this institution.", code="invalid_course"
        )
    return unique


def _set_links(
    db: Session,
    resource: Resource,
    *,
    tags: Sequence[str] | None,
    course_ids: Sequence[uuid.UUID] | None,
) -> None:
    if tags is not None:
        db.execute(delete(ResourceTag).where(ResourceTag.resource_id == resource.id))
        db.add_all(
            ResourceTag(resource_id=resource.id, tag_id=t.id) for t in _resolve_tags(db, tags)
        )
    if course_ids is not None:
        ids = _resolve_courses(db, resource.institution_id, course_ids)
        db.execute(delete(CourseResource).where(CourseResource.resource_id == resource.id))
        db.add_all(
            CourseResource(
                resource_id=resource.id, course_id=cid, institution_id=resource.institution_id
            )
            for cid in ids
        )


def _check_category(db: Session, category_id: uuid.UUID) -> None:
    category = db.get(ResourceCategory, category_id)
    if category is None or not category.is_active:
        raise BadRequestError("Unknown resource category.", code="invalid_category")


# --------------------------------------------------------------------------- create / update / delete


def create_resource(
    db: Session, principal: Principal, data: ResourceCreate, meta: RequestMeta
) -> Resource:
    principal.require(
        "resource:create", data.institution_id
    )  # must be a provider FOR this institution
    institution = db.get(Institution, data.institution_id)
    if institution is None or not institution.is_active:
        raise BadRequestError("Unknown institution.", code="invalid_institution")
    _check_category(db, data.category_id)

    resource = Resource(
        institution_id=data.institution_id, provider_id=principal.user.id, category_id=data.category_id,
        title=data.title, description=data.description, preview_text=data.preview_text,
        access_type=data.access_type, price_ugx=data.price_ugx, academic_year=data.academic_year,
        status=S.DRAFT,
    )  # fmt: skip
    db.add(resource)
    db.flush()
    _set_links(db, resource, tags=data.tags, course_ids=data.course_ids)
    audit.record(
        db, action="resource.created", actor_user_id=principal.user.id, target_type="resource",
        target_id=str(resource.id), institution_id=resource.institution_id, meta=meta,
    )  # fmt: skip
    db.commit()
    return resource


def update_resource(
    db: Session,
    principal: Principal,
    resource_id: uuid.UUID,
    patch: ResourcePatch,
    meta: RequestMeta,
) -> Resource:
    resource = _owned(db, principal, resource_id, "resource:update", lock=True)
    _require_status(resource, EDITABLE)
    changes = patch.model_dump(exclude_unset=True)

    if "category_id" in changes and changes["category_id"] is not None:
        _check_category(db, changes["category_id"])
    for field in ("category_id", "title", "description", "preview_text", "academic_year"):
        if field in changes and (
            changes[field] is not None or field in ("preview_text", "academic_year")
        ):
            setattr(resource, field, changes[field])

    access_type = changes.get("access_type") or resource.access_type
    if "price_ugx" in changes or "access_type" in changes:
        price = changes.get("price_ugx", resource.price_ugx if access_type == "PREMIUM" else None)
        if access_type == "FREE":
            price = None
        elif price is None:
            raise BadRequestError("A premium resource needs a price.", code="price_required")
        resource.access_type, resource.price_ugx = access_type, price

    _set_links(db, resource, tags=changes.get("tags"), course_ids=changes.get("course_ids"))
    if resource.status == S.REJECTED:
        resource.status = S.DRAFT  # editing a rejected resource reopens it for resubmission
    audit.record(
        db, action="resource.updated", actor_user_id=principal.user.id, target_type="resource",
        target_id=str(resource.id), institution_id=resource.institution_id, meta=meta,
    )  # fmt: skip
    db.commit()
    return resource


def add_version(
    db: Session, *, principal: Principal, resource_id: uuid.UUID, upload: UploadFile, changelog: str | None,
    storage: StorageBackend, scanner: MalwareScanner, meta: RequestMeta,
) -> ResourceVersion:  # fmt: skip
    resource = _owned(
        db, principal, resource_id, "resource:update", lock=True
    )  # row lock serialises numbering
    _require_status(resource, EDITABLE)
    count, highest = db.execute(
        select(func.count(), func.coalesce(func.max(ResourceVersion.version_number), 0)).where(
            ResourceVersion.resource_id == resource.id
        )
    ).one()
    if count >= MAX_VERSIONS:
        raise ConflictError(
            f"A resource can have at most {MAX_VERSIONS} versions.", code="too_many_versions"
        )

    stored = store_upload(
        db, upload=upload, owner_id=principal.user.id, key_prefix=f"resources/{resource.id}",
        storage=storage, scanner=scanner, max_bytes=get_settings().max_upload_bytes,
    )  # fmt: skip
    version = ResourceVersion(
        resource_id=resource.id, version_number=highest + 1, file_id=stored.id,
        changelog=changelog, is_current=False, created_by_user_id=principal.user.id,
    )  # fmt: skip
    db.add(version)
    if resource.status == S.REJECTED:
        resource.status = S.DRAFT
    db.flush()
    audit.record(
        db, action="resource.version_added", actor_user_id=principal.user.id, target_type="resource",
        target_id=str(resource.id), institution_id=resource.institution_id,
        details={"version": version.version_number}, meta=meta,
    )  # fmt: skip
    db.commit()
    return version


def delete_draft(
    db: Session,
    principal: Principal,
    resource_id: uuid.UUID,
    storage: StorageBackend,
    meta: RequestMeta,
) -> None:
    resource = _owned(db, principal, resource_id, "resource:delete", lock=True)
    if resource.status != S.DRAFT:
        raise ConflictError(
            "Only drafts can be deleted. Archive published resources instead.", code="not_a_draft"
        )
    file_ids = list(
        db.scalars(
            select(ResourceVersion.file_id).where(ResourceVersion.resource_id == resource.id)
        )
    )
    keys = (
        list(db.scalars(select(StoredFile.storage_key).where(StoredFile.id.in_(file_ids))))
        if file_ids
        else []
    )
    audit.record(
        db, action="resource.deleted", actor_user_id=principal.user.id, target_type="resource",
        target_id=str(resource.id), institution_id=resource.institution_id, meta=meta,
    )  # fmt: skip
    db.delete(resource)  # versions, tags, course links, reviews, bookmarks and downloads cascade
    db.flush()
    if file_ids:
        db.execute(delete(StoredFile).where(StoredFile.id.in_(file_ids)))
    db.commit()
    for key in keys:  # after commit: a failed blob delete leaves an orphan, never a dangling DB row
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001
            logger.exception("blob_delete_failed")


# --------------------------------------------------------------------------- lifecycle transitions


def _latest_version(db: Session, resource: Resource) -> ResourceVersion | None:
    return db.scalar(
        select(ResourceVersion).where(ResourceVersion.resource_id == resource.id)
        .order_by(ResourceVersion.version_number.desc()).limit(1)
    )  # fmt: skip


def submit(
    db: Session, principal: Principal, resource_id: uuid.UUID, meta: RequestMeta
) -> Resource:
    resource = _owned(db, principal, resource_id, "resource:submit", lock=True)
    _require_status(resource, {S.DRAFT})
    version = _latest_version(db, resource)
    if version is None:
        raise BadRequestError("Upload a file before submitting for review.", code="no_file")
    resource.submitted_at = _now()
    _record(
        db,
        principal,
        resource,
        decision="SUBMITTED",
        to_status=S.SUBMITTED,
        reason=None,
        meta=meta,
        version_id=version.id,
    )
    db.commit()
    return resource


def start_review(
    db: Session, principal: Principal, resource_id: uuid.UUID, meta: RequestMeta
) -> Resource:
    resource = _staff(db, principal, resource_id, "resource:review")
    _require_status(resource, {S.SUBMITTED})
    _record(
        db,
        principal,
        resource,
        decision="STARTED",
        to_status=S.UNDER_REVIEW,
        reason=None,
        meta=meta,
    )
    db.commit()
    return resource


def approve(
    db: Session, principal: Principal, resource_id: uuid.UUID, note: str | None, meta: RequestMeta
) -> Resource:
    resource = _staff(db, principal, resource_id, "resource:review")
    _require_status(resource, {S.UNDER_REVIEW})
    _record(
        db, principal, resource, decision="APPROVED", to_status=S.APPROVED, reason=note, meta=meta
    )
    db.commit()
    return resource


def reject(
    db: Session, principal: Principal, resource_id: uuid.UUID, reason: str, meta: RequestMeta
) -> Resource:
    resource = _staff(db, principal, resource_id, "resource:review")
    _require_status(resource, {S.UNDER_REVIEW})
    _record(
        db, principal, resource, decision="REJECTED", to_status=S.REJECTED, reason=reason, meta=meta
    )
    db.commit()
    return resource


def publish(
    db: Session, principal: Principal, resource_id: uuid.UUID, meta: RequestMeta
) -> Resource:
    resource = _staff(db, principal, resource_id, "resource:publish")
    _require_status(resource, {S.APPROVED, S.ARCHIVED})
    version = _latest_version(db, resource)
    if version is None:
        raise BadRequestError("The resource has no file to publish.", code="no_file")
    # Exactly one current version: clear the old marker first (a partial unique index enforces it).
    db.execute(
        update(ResourceVersion)
        .where(ResourceVersion.resource_id == resource.id)
        .values(is_current=False)
    )
    version.is_current = True
    resource.published_at = _now()
    resource.archived_at = None
    _record(
        db,
        principal,
        resource,
        decision="PUBLISHED",
        to_status=S.PUBLISHED,
        reason=None,
        meta=meta,
        version_id=version.id,
    )
    db.commit()
    return resource


def archive(
    db: Session, principal: Principal, resource_id: uuid.UUID, meta: RequestMeta
) -> Resource:
    resource = get_resource(db, resource_id, lock=True)
    if resource.provider_id == principal.user.id:
        principal.require(
            "resource:delete", resource.institution_id
        )  # owners may withdraw their own
    elif not principal.can("resource:publish", resource.institution_id):
        raise _deny(principal, resource)
    _require_status(resource, {S.PUBLISHED})
    resource.archived_at = _now()
    _record(
        db, principal, resource, decision="ARCHIVED", to_status=S.ARCHIVED, reason=None, meta=meta
    )
    db.commit()
    return resource


# --------------------------------------------------------------------------- listings and stats


def list_mine(
    db: Session, principal: Principal, status: str | None, page: int, page_size: int
) -> tuple[list[Resource], int]:
    stmt = select(Resource).where(Resource.provider_id == principal.user.id)
    if status:
        stmt = stmt.where(Resource.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Resource.updated_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )
    return list(rows), total


def review_queue(
    db: Session, principal: Principal, status: str | None, page: int, page_size: int
) -> tuple[list[Resource], int]:
    scope = principal.scope_for("resource:review")
    stmt = select(Resource).where(
        Resource.status.in_([status] if status else [S.SUBMITTED, S.UNDER_REVIEW, S.APPROVED])
    )
    if (
        not scope.platform_wide
    ):  # an institution-scoped reviewer only ever sees their own institutions
        stmt = stmt.where(Resource.institution_id.in_(scope.institution_ids))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Resource.submitted_at.asc().nulls_last())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(rows), total


def resource_stats(db: Session, principal: Principal, resource_id: uuid.UUID) -> StatsOut:
    resource = get_resource(db, resource_id)
    if not (access.is_owner(principal, resource) or access.is_reviewer(principal, resource)):
        raise NotFoundError("Resource not found.")
    since = _now() - timedelta(days=30)
    downloads = (
        db.scalar(
            select(func.count())
            .select_from(ResourceDownload)
            .where(ResourceDownload.resource_id == resource.id)
        )
        or 0
    )
    recent = (
        db.scalar(
            select(func.count())
            .select_from(ResourceDownload)
            .where(
                ResourceDownload.resource_id == resource.id, ResourceDownload.created_at >= since
            )
        )
        or 0
    )
    bookmarks = (
        db.scalar(
            select(func.count()).select_from(Bookmark).where(Bookmark.resource_id == resource.id)
        )
        or 0
    )
    entitlements = (
        db.scalar(
            select(func.count())
            .select_from(Entitlement)
            .where(Entitlement.resource_id == resource.id, Entitlement.status == "ACTIVE")
        )
        or 0
    )
    return StatsOut(
        downloads_total=downloads,
        downloads_last_30_days=recent,
        bookmarks=bookmarks,
        active_entitlements=entitlements,
    )
