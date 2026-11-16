"""Notification endpoints (recipient-protected)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession
from app.core.responses import Envelope, ok
from app.modules.auth.deps import require_permission
from app.modules.auth.schemas import MessageOut
from app.modules.notifications import service
from app.modules.notifications.schemas import MarkReadIn, NotificationOut, UnreadCountOut
from app.modules.rbac.principal import Principal

router = APIRouter(prefix="/notifications", tags=["notifications"])

_RequireRead = Annotated[Principal, Depends(require_permission("notification:read"))]


@router.get(
    "",
    response_model=Envelope[list[NotificationOut]],
    summary="List my notifications",
)
def list_notifications(
    db: DbSession,
    principal: _RequireRead,
    unread_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Envelope[list[NotificationOut]]:
    items, total = service.list_notifications(
        db,
        recipient_id=principal.user.id,
        unread_only=unread_only,
        page=page,
        page_size=page_size,
    )
    return ok(
        [NotificationOut.model_validate(n) for n in items],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@router.get(
    "/unread-count",
    response_model=Envelope[UnreadCountOut],
    summary="Unread notification count",
)
def unread_count(
    db: DbSession,
    principal: _RequireRead,
) -> Envelope[UnreadCountOut]:
    count = service.get_unread_count(db, recipient_id=principal.user.id)
    return ok(UnreadCountOut(count=count))


@router.post(
    "/mark-read",
    response_model=Envelope[MessageOut],
    summary="Mark notifications as read",
)
def mark_read(
    body: MarkReadIn,
    db: DbSession,
    principal: _RequireRead,
) -> Envelope[MessageOut]:
    n = service.mark_read(db, recipient_id=principal.user.id, ids=body.ids or None)
    return ok(MessageOut(message=f"{n} notification{'s' if n != 1 else ''} marked as read."))


@router.post(
    "/process-outbox",
    response_model=Envelope[MessageOut],
    summary="Process pending outbox entries (internal / admin use)",
    include_in_schema=False,
)
def process_outbox(
    db: DbSession,
    principal: Annotated[Principal, Depends(require_permission("analytics:read"))],
) -> Envelope[MessageOut]:
    """Trigger outbox processing synchronously.  In production this should be called by a scheduler."""
    n = service.process_pending_outbox(db)
    return ok(MessageOut(message=f"Processed {n} outbox {'entry' if n == 1 else 'entries'}."))
