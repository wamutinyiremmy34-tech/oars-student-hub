"""Advertising API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ─── Public (ad-serving) ──────────────────────────────────────────────────────


class AdServedOut(BaseModel):
    """Minimal ad representation returned to the frontend.  No internal or advertiser-only data."""

    id: uuid.UUID
    title: str
    body: str | None
    image_url: str | None
    click_url: str | None
    placement: str

    model_config = {"from_attributes": True}


# ─── Admin ────────────────────────────────────────────────────────────────────


class AdvertiserOut(BaseModel):
    id: uuid.UUID
    name: str
    contact_email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdvertiserIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    contact_email: str = Field(max_length=254)


class CampaignOut(BaseModel):
    id: uuid.UUID
    advertiser_id: uuid.UUID
    name: str
    starts_at: datetime | None
    ends_at: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignIn(BaseModel):
    advertiser_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class AdOut(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    status: str
    title: str
    body: str | None
    image_url: str | None
    click_url: str | None
    placement: str
    starts_at: datetime | None
    ends_at: datetime | None
    rejection_reason: str | None
    target_institution_ids: list[uuid.UUID | None]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdIn(BaseModel):
    campaign_id: uuid.UUID
    title: str = Field(min_length=2, max_length=200)
    body: str | None = Field(default=None, max_length=1000)
    image_url: str | None = Field(default=None, max_length=500)
    click_url: str | None = Field(default=None, max_length=500)
    placement: str = Field(default="dashboard_banner", max_length=50)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    # Institution IDs for targeting. Empty list = platform-wide.
    target_institution_ids: list[uuid.UUID] = Field(default_factory=list)


class AdStatusIn(BaseModel):
    status: str = Field(description="New status: ACTIVE, PAUSED, ARCHIVED, REJECTED")
    rejection_reason: str | None = None


class AdEventIn(BaseModel):
    event_type: str = Field(description="'IMPRESSION' or 'CLICK'")
    institution_id: uuid.UUID | None = None
    session_token: str | None = Field(default=None, max_length=64)


class AdMetricsOut(BaseModel):
    advertisement_id: uuid.UUID
    impressions: int
    clicks: int


class PlatformAnalyticsOut(BaseModel):
    total_users: int
    total_resources: int
    published_resources: int
    total_orders: int
    completed_orders: int
    total_impressions: int
    total_clicks: int
