import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DbSession
from app.core.errors import ConflictError, PayloadTooLargeError
from app.core.http import RequestMetaDep
from app.core.responses import Envelope, ok
from app.modules.academic.service import escape_like
from app.modules.auth.deps import CurrentPrincipal, OptionalPrincipal, require_permission
from app.modules.auth.schemas import MessageOut
from app.modules.rbac.principal import Principal
from app.modules.resources import access, bookmarks, presenters, search, service
from app.modules.resources.models import ResourceCategory, Tag
from app.modules.resources.schemas import (
    CategoryIn,
    CategoryOut,
    DownloadOut,
    EntitlementOut,
    GrantEntitlementIn,
    NoteIn,
    RejectIn,
    ResourceCreate,
    ResourceDetail,
    ResourcePatch,
    ResourceSummary,
    SearchParams,
    StatsOut,
    VersionOut,
)
from app.providers.deps import ScannerDep, StorageDep

resources_router = APIRouter(prefix="/resources", tags=["resources"])
search_router = APIRouter(prefix="/search", tags=["search"])
bookmarks_router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])
categories_router = APIRouter(tags=["resources"])

Page = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=50)]
StatusFilter = Annotated[str | None, Query(pattern="^[A-Z_]{4,20}$")]


def _page_meta(page: int, page_size: int, total: int) -> dict[str, int]:
    return {"page": page, "page_size": page_size, "total": total}


def _upload_limit(request: Request) -> None:
    """Cheap early rejection of oversized uploads. A reverse proxy must also cap request bodies."""
    declared = request.headers.get("content-length")
    limit = get_settings().max_upload_bytes + 1024 * 1024  # multipart overhead
    if declared and declared.isdigit() and int(declared) > limit:
        raise PayloadTooLargeError("The uploaded file is too large.", code="file_too_large")


# ------------------------------------------------------------------ public catalogue
@resources_router.get(
    "", response_model=Envelope[list[ResourceSummary]], summary="Browse published resources"
)
def browse(
    db: DbSession, viewer: OptionalPrincipal, params: Annotated[SearchParams, Query()]
) -> Envelope[list[ResourceSummary]]:
    rows, total = search.search_resources(db, params)
    return ok(
        presenters.to_summaries(db, rows, viewer),
        meta=_page_meta(params.page, params.page_size, total),
    )


@search_router.get(
    "", response_model=Envelope[list[ResourceSummary]], summary="Search published resources"
)
def search_endpoint(
    db: DbSession, viewer: OptionalPrincipal, params: Annotated[SearchParams, Query()]
) -> Envelope[list[ResourceSummary]]:
    rows, total = search.search_resources(db, params)
    return ok(
        presenters.to_summaries(db, rows, viewer),
        meta=_page_meta(params.page, params.page_size, total),
    )


# ------------------------------------------------------------------ provider and moderator lists (static paths first)
@resources_router.get("/mine", response_model=Envelope[list[ResourceSummary]])
def my_resources(
    db: DbSession,
    principal: Annotated[Principal, Depends(require_permission("resource:create"))],
    status: StatusFilter = None,
    page: Page = 1,
    page_size: PageSize = 12,
) -> Envelope[list[ResourceSummary]]:
    rows, total = service.list_mine(db, principal, status, page, page_size)
    return ok(presenters.to_summaries(db, rows, principal), meta=_page_meta(page, page_size, total))


@resources_router.get("/review-queue", response_model=Envelope[list[ResourceSummary]])
def review_queue(
    db: DbSession,
    principal: Annotated[Principal, Depends(require_permission("resource:review"))],
    status: StatusFilter = None,
    page: Page = 1,
    page_size: PageSize = 12,
) -> Envelope[list[ResourceSummary]]:
    rows, total = service.review_queue(db, principal, status, page, page_size)
    return ok(presenters.to_summaries(db, rows, principal), meta=_page_meta(page, page_size, total))


# ------------------------------------------------------------------ create / read / update
@resources_router.post("", status_code=201, response_model=Envelope[ResourceDetail])
def create_resource(
    body: ResourceCreate,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:create"))],
) -> Envelope[ResourceDetail]:
    resource = service.create_resource(db, principal, body, meta)
    return ok(presenters.to_detail(db, resource, principal))


@resources_router.get("/{resource_id}", response_model=Envelope[ResourceDetail])
def get_resource(
    resource_id: uuid.UUID, db: DbSession, viewer: OptionalPrincipal
) -> Envelope[ResourceDetail]:
    resource = service.get_visible_resource(db, viewer, resource_id)
    return ok(presenters.to_detail(db, resource, viewer))


@resources_router.patch("/{resource_id}", response_model=Envelope[ResourceDetail])
def update_resource(
    resource_id: uuid.UUID,
    body: ResourcePatch,
    db: DbSession,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:update"))],
) -> Envelope[ResourceDetail]:
    resource = service.update_resource(db, principal, resource_id, body, meta)
    return ok(presenters.to_detail(db, resource, principal))


@resources_router.delete("/{resource_id}", response_model=Envelope[MessageOut])
def delete_resource(
    resource_id: uuid.UUID,
    db: DbSession,
    storage: StorageDep,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:delete"))],
) -> Envelope[MessageOut]:
    service.delete_draft(db, principal, resource_id, storage, meta)
    return ok(MessageOut(message="Draft deleted."))


@resources_router.post(
    "/{resource_id}/versions",
    status_code=201,
    response_model=Envelope[VersionOut],
    dependencies=[Depends(_upload_limit)],
)
def upload_version(
    resource_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    db: DbSession,
    storage: StorageDep,
    scanner: ScannerDep,
    meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:update"))],
    changelog: Annotated[str | None, Form(max_length=500)] = None,
) -> Envelope[VersionOut]:
    version = service.add_version(
        db, principal=principal, resource_id=resource_id, upload=file, changelog=changelog,
        storage=storage, scanner=scanner, meta=meta,
    )  # fmt: skip
    detail = presenters.to_detail(db, service.get_resource(db, resource_id), principal)
    created = next(v for v in detail.versions if v.id == version.id)
    return ok(created)


# ------------------------------------------------------------------ lifecycle
def _detail(db: DbSession, resource, principal: Principal) -> Envelope[ResourceDetail]:  # type: ignore[no-untyped-def]
    return ok(presenters.to_detail(db, resource, principal))


@resources_router.post("/{resource_id}/submit", response_model=Envelope[ResourceDetail])
def submit(
    resource_id: uuid.UUID, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:submit"))],
) -> Envelope[ResourceDetail]:  # fmt: skip
    return _detail(db, service.submit(db, principal, resource_id, meta), principal)


@resources_router.post("/{resource_id}/start-review", response_model=Envelope[ResourceDetail])
def start_review(
    resource_id: uuid.UUID, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:review"))],
) -> Envelope[ResourceDetail]:  # fmt: skip
    return _detail(db, service.start_review(db, principal, resource_id, meta), principal)


@resources_router.post("/{resource_id}/approve", response_model=Envelope[ResourceDetail])
def approve(
    resource_id: uuid.UUID, body: NoteIn, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:review"))],
) -> Envelope[ResourceDetail]:  # fmt: skip
    return _detail(db, service.approve(db, principal, resource_id, body.note, meta), principal)


@resources_router.post("/{resource_id}/reject", response_model=Envelope[ResourceDetail])
def reject(
    resource_id: uuid.UUID, body: RejectIn, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:review"))],
) -> Envelope[ResourceDetail]:  # fmt: skip
    return _detail(db, service.reject(db, principal, resource_id, body.reason, meta), principal)


@resources_router.post("/{resource_id}/publish", response_model=Envelope[ResourceDetail])
def publish(
    resource_id: uuid.UUID, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("resource:publish"))],
) -> Envelope[ResourceDetail]:  # fmt: skip
    return _detail(db, service.publish(db, principal, resource_id, meta), principal)


@resources_router.post("/{resource_id}/archive", response_model=Envelope[ResourceDetail])
def archive(
    resource_id: uuid.UUID, db: DbSession, meta: RequestMetaDep, principal: CurrentPrincipal
) -> Envelope[ResourceDetail]:
    # Owners (resource:delete) and publishers (resource:publish) may archive; the service decides which applies.
    return _detail(db, service.archive(db, principal, resource_id, meta), principal)


# ------------------------------------------------------------------ download, stats, entitlements
@resources_router.post("/{resource_id}/download", response_model=Envelope[DownloadOut])
def download(
    resource_id: uuid.UUID,
    db: DbSession,
    storage: StorageDep,
    meta: RequestMetaDep,
    principal: CurrentPrincipal,
) -> Envelope[DownloadOut]:
    return ok(
        access.create_download(
            db, principal=principal, resource_id=resource_id, storage=storage, meta=meta
        )
    )


@resources_router.get("/{resource_id}/stats", response_model=Envelope[StatsOut])
def stats(resource_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal) -> Envelope[StatsOut]:
    return ok(service.resource_stats(db, principal, resource_id))


@resources_router.post(
    "/{resource_id}/entitlements", status_code=201, response_model=Envelope[EntitlementOut]
)
def grant_entitlement(
    resource_id: uuid.UUID, body: GrantEntitlementIn, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("entitlement:manage"))],
) -> Envelope[EntitlementOut]:  # fmt: skip
    e = access.grant_entitlement_as_admin(
        db, principal=principal, resource_id=resource_id, user_id=body.user_id,
        expires_at=body.expires_at, reference=body.source_reference, meta=meta,
    )  # fmt: skip
    return ok(
        EntitlementOut(
            resource_id=e.resource_id,
            user_id=e.user_id,
            status=e.status,
            source=e.source,
            expires_at=e.expires_at,
        )
    )


@resources_router.delete(
    "/{resource_id}/entitlements/{user_id}", response_model=Envelope[MessageOut]
)
def revoke_entitlement(
    resource_id: uuid.UUID, user_id: uuid.UUID, db: DbSession, meta: RequestMetaDep,
    principal: Annotated[Principal, Depends(require_permission("entitlement:manage"))],
) -> Envelope[MessageOut]:  # fmt: skip
    access.revoke_entitlement(
        db, principal=principal, resource_id=resource_id, user_id=user_id, meta=meta
    )
    return ok(MessageOut(message="Access revoked."))


# ------------------------------------------------------------------ bookmarks (own only: no user id anywhere)
@bookmarks_router.get("", response_model=Envelope[list[ResourceSummary]])
def list_bookmarks(
    db: DbSession, principal: CurrentPrincipal, page: Page = 1, page_size: PageSize = 12
) -> Envelope[list[ResourceSummary]]:
    rows, total = bookmarks.list_bookmarked(db, principal, page, page_size)
    return ok(presenters.to_summaries(db, rows, principal), meta=_page_meta(page, page_size, total))


@bookmarks_router.put("/{resource_id}", response_model=Envelope[MessageOut])
def add_bookmark(
    resource_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal
) -> Envelope[MessageOut]:
    bookmarks.add_bookmark(db, principal, resource_id)
    return ok(MessageOut(message="Bookmarked."))


@bookmarks_router.delete("/{resource_id}", response_model=Envelope[MessageOut])
def remove_bookmark(
    resource_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal
) -> Envelope[MessageOut]:
    bookmarks.remove_bookmark(db, principal, resource_id)
    return ok(MessageOut(message="Bookmark removed."))


# ------------------------------------------------------------------ categories and tags
@categories_router.get("/categories", response_model=Envelope[list[CategoryOut]])
def list_categories(db: DbSession) -> Envelope[list[CategoryOut]]:
    rows = db.scalars(
        select(ResourceCategory)
        .where(ResourceCategory.is_active.is_(True))
        .order_by(ResourceCategory.sort_order, ResourceCategory.name)
    )
    return ok(
        [CategoryOut(id=c.id, name=c.name, slug=c.slug, description=c.description) for c in rows]
    )


@categories_router.post("/categories", status_code=201, response_model=Envelope[CategoryOut])
def create_category(
    body: CategoryIn, db: DbSession,
    principal: Annotated[Principal, Depends(require_permission("category:manage"))],
) -> Envelope[CategoryOut]:  # fmt: skip
    principal.require(
        "category:manage", None
    )  # platform-wide only: categories are shared by all universities
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:80]
    if db.scalar(
        select(ResourceCategory.id).where(
            (ResourceCategory.slug == slug) | (ResourceCategory.name == body.name)
        )
    ):
        raise ConflictError("That category already exists.", code="already_exists")
    category = ResourceCategory(
        name=body.name, slug=slug, description=body.description, sort_order=body.sort_order
    )
    db.add(category)
    db.commit()
    return ok(
        CategoryOut(
            id=category.id, name=category.name, slug=category.slug, description=category.description
        )
    )


@categories_router.get(
    "/tags", response_model=Envelope[list[str]], summary="Tag suggestions (prefix match)"
)
def suggest_tags(
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=40)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> Envelope[list[str]]:
    rows = db.scalars(
        select(Tag.name)
        .where(Tag.name.like(f"{escape_like(q.lower())}%", escape="\\"))
        .order_by(Tag.name)
        .limit(limit)
    )
    return ok(list(rows))
