import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.modules.rbac.principal import Principal
from app.modules.resources.models import Bookmark, Resource, ResourceStatus


def add_bookmark(db: Session, principal: Principal, resource_id: uuid.UUID) -> None:
    """Idempotent. Only published resources can be bookmarked; the user id always comes from the token."""
    resource = db.get(Resource, resource_id)
    if resource is None or resource.status != ResourceStatus.PUBLISHED:
        raise NotFoundError("Resource not found.")
    exists = db.scalar(
        select(Bookmark.id).where(
            Bookmark.user_id == principal.user.id, Bookmark.resource_id == resource_id
        )
    )
    if exists is not None:
        return
    db.add(Bookmark(user_id=principal.user.id, resource_id=resource_id))
    try:
        db.commit()
    except IntegrityError:  # a concurrent identical request won the race: that is fine
        db.rollback()


def remove_bookmark(db: Session, principal: Principal, resource_id: uuid.UUID) -> None:
    db.execute(
        delete(Bookmark).where(
            Bookmark.user_id == principal.user.id, Bookmark.resource_id == resource_id
        )
    )
    db.commit()


def list_bookmarked(
    db: Session, principal: Principal, page: int, page_size: int
) -> tuple[list[Resource], int]:
    stmt = (
        select(Resource)
        .join(Bookmark, Bookmark.resource_id == Resource.id)
        .where(Bookmark.user_id == principal.user.id, Resource.status == ResourceStatus.PUBLISHED)
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Bookmark.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )
    return list(rows), total
