"""Admin and student-dashboard endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import DbSession
from app.core.responses import Envelope, ok
from app.modules.admin.schemas import (
    AdminUserListOut,
    AdminUserRow,
    AuditLogListOut,
    AuditLogOut,
    DashboardOut,
    RecentOrderOut,
    RecentResourceOut,
)
from app.modules.audit.models import AuditLog
from app.modules.auth.deps import CurrentPrincipal, require_permission
from app.modules.notifications.service import get_unread_count
from app.modules.printing.models import PrintOrder
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.principal import Principal
from app.modules.resources.models import Bookmark, Resource, ResourceCategory
from app.modules.users.models import User

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])

_RequireAuditRead = Annotated[Principal, Depends(require_permission("audit:read"))]
_RequireUserRead = Annotated[Principal, Depends(require_permission("user:read"))]


# ─── Student / user dashboard ─────────────────────────────────────────────────


@dashboard_router.get(
    "",
    response_model=Envelope[DashboardOut],
    summary="Student dashboard data",
)
def get_dashboard(
    db: DbSession,
    principal: CurrentPrincipal,
) -> Envelope[DashboardOut]:
    user = principal.user

    # Unread notifications count.
    unread = get_unread_count(db, recipient_id=user.id)

    # Recent resources the user owns or has viewed (we use bookmarks as "saved resources").
    recent_resources: list[RecentResourceOut] = []
    if principal.has_any_scope("resource:create"):
        rows = list(
            db.execute(
                select(Resource, ResourceCategory)
                .join(ResourceCategory, Resource.category_id == ResourceCategory.id)
                .where(Resource.provider_id == user.id)
                .order_by(Resource.created_at.desc())
                .limit(5)
            )
        )
        for resource, category in rows:
            recent_resources.append(
                RecentResourceOut(
                    id=resource.id,
                    title=resource.title,
                    access_type=resource.access_type,
                    category_name=category.name,
                    institution_name=str(resource.institution_id),
                )
            )

    # Recent print orders.
    recent_orders: list[RecentOrderOut] = []
    if principal.has_any_scope("order:read"):
        orders = list(
            db.scalars(
                select(PrintOrder)
                .where(PrintOrder.student_id == user.id)
                .order_by(PrintOrder.created_at.desc())
                .limit(5)
            )
        )
        for order in orders:
            from app.modules.printing.models import PrintShop

            shop = db.get(PrintShop, order.shop_id)
            recent_orders.append(
                RecentOrderOut(
                    id=order.id,
                    status=order.status,
                    payment_status=order.payment_status,
                    shop_name=shop.name if shop else "Unknown",
                    total_ugx=order.total_ugx,
                    created_at=order.created_at,
                )
            )

    # Bookmarked resources count.
    bookmarked_count = db.scalar(select(func.count()).where(Bookmark.user_id == user.id)) or 0

    greeting = f"Welcome back, {user.full_name.split()[0]}!"

    return ok(
        DashboardOut(
            greeting=greeting,
            unread_notifications=unread,
            recent_resources=recent_resources,
            recent_orders=recent_orders,
            bookmarked_count=bookmarked_count,
        )
    )


# ─── Admin: user management ───────────────────────────────────────────────────


@admin_router.get(
    "/users",
    response_model=Envelope[AdminUserListOut],
    summary="List users (admin)",
)
def list_users(
    db: DbSession,
    principal: _RequireUserRead,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> Envelope[AdminUserListOut]:
    principal.scope_for("user:read")

    query = select(User)
    if q:
        term = f"%{q.lower()}%"
        query = query.where(
            (func.lower(User.email).like(term)) | (func.lower(User.full_name).like(term))
        )
    if status:
        query = query.where(User.status == status.upper())

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    offset = (max(1, page) - 1) * page_size
    users = list(db.scalars(query.order_by(User.created_at.desc()).offset(offset).limit(page_size)))

    items = []
    for user in users:
        roles = list(
            db.scalars(
                select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
            )
        )
        items.append(
            AdminUserRow(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                status=user.status,
                email_verified=user.email_verified_at is not None,
                created_at=user.created_at,
                roles=roles,
            )
        )

    return ok(
        AdminUserListOut(items=items, total=total, page=page, page_size=page_size),
        meta={"page": page, "page_size": page_size, "total": total},
    )


# ─── Admin: audit log read ────────────────────────────────────────────────────


@admin_router.get(
    "/audit-logs",
    response_model=Envelope[AuditLogListOut],
    summary="Read audit logs (admin)",
)
def read_audit_logs(
    db: DbSession,
    principal: _RequireAuditRead,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    institution_id: uuid.UUID | None = Query(default=None),
) -> Envelope[AuditLogListOut]:
    scope = principal.scope_for("audit:read")
    q = select(AuditLog)

    # Institution scoping: an institution-scoped admin sees only their institution's logs.
    if not scope.platform_wide and scope.institution_ids:
        q = q.where(AuditLog.institution_id.in_(scope.institution_ids))

    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if actor_user_id:
        q = q.where(AuditLog.actor_user_id == actor_user_id)
    if institution_id:
        if scope.platform_wide or institution_id in scope.institution_ids:
            q = q.where(AuditLog.institution_id == institution_id)

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    offset = (max(1, page) - 1) * page_size
    logs = list(db.scalars(q.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)))

    return ok(
        AuditLogListOut(
            items=[AuditLogOut.model_validate(log) for log in logs],
            total=total,
            page=page,
            page_size=page_size,
        ),
        meta={"page": page, "page_size": page_size, "total": total},
    )
