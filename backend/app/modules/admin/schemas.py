"""Admin and dashboard API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel

# ─── Student dashboard ────────────────────────────────────────────────────────


class RecentResourceOut(BaseModel):
    id: uuid.UUID
    title: str
    access_type: str
    category_name: str
    institution_name: str

    model_config = {"from_attributes": True}


class RecentOrderOut(BaseModel):
    id: uuid.UUID
    status: str
    payment_status: str
    shop_name: str
    total_ugx: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardOut(BaseModel):
    greeting: str
    unread_notifications: int
    recent_resources: list[RecentResourceOut]
    recent_orders: list[RecentOrderOut]
    bookmarked_count: int


# ─── Admin user list ──────────────────────────────────────────────────────────


class AdminUserRow(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    status: str
    email_verified: bool
    created_at: datetime
    roles: list[str]


class AdminUserListOut(BaseModel):
    items: list[AdminUserRow]
    total: int
    page: int
    page_size: int


# ─── Audit log read ───────────────────────────────────────────────────────────


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    outcome: str
    target_type: str | None
    target_id: str | None
    institution_id: uuid.UUID | None
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListOut(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
