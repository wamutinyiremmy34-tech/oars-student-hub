"""Turns ORM rows into API schemas with a fixed number of queries per page (no N+1)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.academic.models import Course
from app.modules.files.models import StoredFile
from app.modules.institutions.models import Institution
from app.modules.rbac.principal import Principal
from app.modules.resources import access
from app.modules.resources.models import (
    Bookmark,
    CourseResource,
    Resource,
    ResourceCategory,
    ResourceReview,
    ResourceStatus,
    ResourceTag,
    ResourceVersion,
    Tag,
)
from app.modules.resources.schemas import (
    CategoryOut,
    CourseRef,
    ResourceDetail,
    ResourceSummary,
    ReviewOut,
    VersionOut,
    ViewerOut,
)
from app.modules.users.models import User

EXCERPT_CHARS = 180


def _version_out(version: ResourceVersion, stored: StoredFile) -> VersionOut:
    return VersionOut(
        id=version.id,
        version_number=version.version_number,
        filename=stored.original_filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        is_current=version.is_current,
        changelog=version.changelog,
        created_at=version.created_at,
    )


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT_CHARS else text[: EXCERPT_CHARS - 1].rstrip() + "…"


def to_summaries(
    db: Session, resources: Sequence[Resource], viewer: Principal | None
) -> list[ResourceSummary]:
    if not resources:
        return []
    ids = [r.id for r in resources]

    tags: dict[uuid.UUID, list[str]] = {}
    for rid, name in db.execute(
        select(ResourceTag.resource_id, Tag.name)
        .join(Tag, Tag.id == ResourceTag.tag_id)
        .where(ResourceTag.resource_id.in_(ids))
        .order_by(Tag.name)
    ):
        tags.setdefault(rid, []).append(name)

    courses: dict[uuid.UUID, list[CourseRef]] = {}
    for rid, cid, code, title in db.execute(
        select(CourseResource.resource_id, Course.id, Course.code, Course.title)
        .join(Course, Course.id == CourseResource.course_id)
        .where(CourseResource.resource_id.in_(ids))
        .order_by(Course.code)
    ):
        courses.setdefault(rid, []).append(CourseRef(id=cid, code=code, title=title))

    categories = {
        c.id: c
        for c in db.scalars(
            select(ResourceCategory).where(
                ResourceCategory.id.in_({r.category_id for r in resources})
            )
        )
    }
    institutions = dict(
        db.execute(
            select(Institution.id, Institution.name).where(
                Institution.id.in_({r.institution_id for r in resources})
            )
        ).all()
    )
    providers = dict(
        db.execute(
            select(User.id, User.full_name).where(User.id.in_({r.provider_id for r in resources}))
        ).all()
    )

    files: dict[uuid.UUID, VersionOut] = {}
    rows = db.execute(
        select(ResourceVersion, StoredFile)
        .join(StoredFile, StoredFile.id == ResourceVersion.file_id)
        .where(ResourceVersion.resource_id.in_(ids))
        .order_by(ResourceVersion.version_number)
    ).all()
    for version, stored in rows:  # ascending, so the last one wins unless a current version exists
        existing = files.get(version.resource_id)
        if existing is None or not existing.is_current:
            files[version.resource_id] = _version_out(version, stored)
        if version.is_current:
            files[version.resource_id] = _version_out(version, stored)

    bookmarked: set[uuid.UUID] = set()
    if viewer is not None:
        bookmarked = set(
            db.scalars(
                select(Bookmark.resource_id).where(
                    Bookmark.user_id == viewer.user.id, Bookmark.resource_id.in_(ids)
                )
            )
        )

    out: list[ResourceSummary] = []
    for r in resources:
        category = categories[r.category_id]
        out.append(
            ResourceSummary(
                id=r.id,
                title=r.title,
                excerpt=_excerpt(r.description),
                access_type=r.access_type,
                price_ugx=r.price_ugx,
                status=r.status,
                institution_id=r.institution_id,
                institution_name=institutions.get(r.institution_id, ""),
                category=CategoryOut(
                    id=category.id,
                    name=category.name,
                    slug=category.slug,
                    description=category.description,
                ),
                tags=tags.get(r.id, []),
                courses=courses.get(r.id, []),
                academic_year=r.academic_year,
                provider_name=providers.get(r.provider_id, "Unknown"),
                published_at=r.published_at,
                file=files.get(r.id),
                is_bookmarked=r.id in bookmarked,
            )
        )
    return out


def to_detail(db: Session, resource: Resource, viewer: Principal | None) -> ResourceDetail:
    summary = to_summaries(db, [resource], viewer)[0]
    owner = access.is_owner(viewer, resource)
    staff = access.is_reviewer(viewer, resource)
    decision = access.evaluate_access(db, viewer, resource)

    versions: list[VersionOut] = []
    if owner or staff:  # only owners and staff see history; the public sees the current file only
        rows = db.execute(
            select(ResourceVersion, StoredFile)
            .join(StoredFile, StoredFile.id == ResourceVersion.file_id)
            .where(ResourceVersion.resource_id == resource.id)
            .order_by(ResourceVersion.version_number.desc())
        ).all()
        versions = [_version_out(v, s) for v, s in rows]

    latest_review: ReviewOut | None = None
    if owner or staff:
        review = db.scalar(
            select(ResourceReview)
            .where(ResourceReview.resource_id == resource.id)
            .order_by(ResourceReview.created_at.desc())
            .limit(1)
        )
        if review is not None:
            latest_review = ReviewOut(
                decision=review.decision, reason=review.reason, created_at=review.created_at
            )

    can_publish = viewer is not None and viewer.can("resource:publish", resource.institution_id)
    separation_ok = viewer is not None and (
        not owner or viewer.can("resource:review_own", resource.institution_id)
    )
    viewer_out = ViewerOut(
        is_owner=owner,
        can_download=decision.can_download,
        download_block_reason=decision.reason,
        is_bookmarked=summary.is_bookmarked,
        can_review=bool(
            viewer and viewer.can("resource:review", resource.institution_id) and separation_ok
        ),
        can_publish=bool(can_publish and separation_ok),
        entitlement_status=decision.entitlement_status,
    )
    data = summary.model_dump()
    return ResourceDetail(
        **data,
        description=resource.description,
        preview_text=resource.preview_text,
        versions=versions,
        viewer=viewer_out,
        latest_review=latest_review,
    )


def published_only(resource: Resource) -> bool:
    return resource.status == ResourceStatus.PUBLISHED
