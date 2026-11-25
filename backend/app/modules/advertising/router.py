"""Advertising and analytics API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession
from app.core.http import RequestMetaDep
from app.core.responses import Envelope, ok
from app.modules.advertising import service
from app.modules.advertising.schemas import (
    AdEventIn,
    AdIn,
    AdMetricsOut,
    AdOut,
    AdServedOut,
    AdStatusIn,
    AdvertiserIn,
    AdvertiserOut,
    CampaignIn,
    CampaignOut,
    CampaignPatch,
    PlatformAnalyticsOut,
)
from app.modules.auth.deps import OptionalPrincipal, require_permission
from app.modules.auth.schemas import MessageOut
from app.modules.rbac.principal import Principal

ads_router = APIRouter(prefix="/ads", tags=["advertising"])
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])

_RequireManage = Annotated[Principal, Depends(require_permission("advertisement:manage"))]
_RequireAnalytics = Annotated[Principal, Depends(require_permission("analytics:read"))]


# ─── Ad serving (public) ──────────────────────────────────────────────────────


@ads_router.get(
    "",
    response_model=Envelope[list[AdServedOut]],
    summary="Get ads for a placement",
)
def get_ads(
    db: DbSession,
    _principal: OptionalPrincipal,
    placement: str = Query(default="dashboard_banner", max_length=50),
    institution_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=3, ge=1, le=10),
) -> Envelope[list[AdServedOut]]:
    ads = service.get_active_ads(
        db, placement=placement, institution_id=institution_id, limit=limit
    )
    return ok([AdServedOut.model_validate(ad) for ad in ads])


@ads_router.post(
    "/{ad_id}/events",
    response_model=Envelope[MessageOut],
    status_code=202,
    summary="Record an impression or click",
)
def record_event(
    ad_id: uuid.UUID,
    body: AdEventIn,
    db: DbSession,
    _principal: OptionalPrincipal,
) -> Envelope[MessageOut]:
    try:
        service.record_event(
            db,
            ad_id=ad_id,
            event_type=body.event_type,
            institution_id=body.institution_id,
            session_token=body.session_token,
        )
    except Exception:  # noqa: BLE001
        # Event recording failures must never break the user experience.
        pass
    return ok(MessageOut(message="Event recorded."))


# ─── Advertiser management (admin) ───────────────────────────────────────────


@ads_router.get(
    "/advertisers",
    response_model=Envelope[list[AdvertiserOut]],
    summary="List advertisers",
)
def list_advertisers(
    db: DbSession,
    _principal: _RequireManage,
) -> Envelope[list[AdvertiserOut]]:
    return ok([AdvertiserOut.model_validate(a) for a in service.list_advertisers(db)])


@ads_router.post(
    "/advertisers",
    response_model=Envelope[AdvertiserOut],
    status_code=201,
    summary="Create advertiser",
)
def create_advertiser(
    body: AdvertiserIn,
    db: DbSession,
    _principal: _RequireManage,
) -> Envelope[AdvertiserOut]:
    adv = service.create_advertiser(db, name=body.name, contact_email=body.contact_email)
    return ok(AdvertiserOut.model_validate(adv))


# ─── Campaign management (admin) ─────────────────────────────────────────────


@ads_router.get(
    "/campaigns",
    response_model=Envelope[list[CampaignOut]],
    summary="List campaigns",
)
def list_campaigns(
    db: DbSession,
    _principal: _RequireManage,
    advertiser_id: uuid.UUID | None = Query(default=None),
) -> Envelope[list[CampaignOut]]:
    return ok(
        [
            CampaignOut.model_validate(c)
            for c in service.list_campaigns(db, advertiser_id=advertiser_id)
        ]
    )


@ads_router.post(
    "/campaigns",
    response_model=Envelope[CampaignOut],
    status_code=201,
    summary="Create campaign",
)
def create_campaign(
    body: CampaignIn,
    db: DbSession,
    _principal: _RequireManage,
) -> Envelope[CampaignOut]:
    c = service.create_campaign(
        db,
        advertiser_id=body.advertiser_id,
        name=body.name,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    return ok(CampaignOut.model_validate(c))


@ads_router.patch(
    "/campaigns/{campaign_id}",
    response_model=Envelope[CampaignOut],
    summary="Update campaign",
)
def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignPatch,
    db: DbSession,
    _principal: _RequireManage,
) -> Envelope[CampaignOut]:
    c = service.update_campaign(
        db,
        campaign_id=campaign_id,
        name=body.name,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        is_active=body.is_active,
    )
    return ok(CampaignOut.model_validate(c))


# ─── Advertisement CRUD (admin) ───────────────────────────────────────────────


@ads_router.get(
    "/advertisements",
    response_model=Envelope[list[AdOut]],
    summary="List advertisements",
)
def list_advertisements(
    db: DbSession,
    principal: _RequireManage,
    campaign_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
) -> Envelope[list[AdOut]]:
    ads = service.list_advertisements(db, campaign_id=campaign_id, status=status)
    return ok([_to_ad_out(ad) for ad in ads])


@ads_router.post(
    "/advertisements",
    response_model=Envelope[AdOut],
    status_code=201,
    summary="Create advertisement",
)
def create_advertisement(
    body: AdIn,
    db: DbSession,
    principal: _RequireManage,
) -> Envelope[AdOut]:
    ad = service.create_advertisement(
        db,
        actor=principal,
        campaign_id=body.campaign_id,
        title=body.title,
        body=body.body,
        image_url=body.image_url,
        click_url=body.click_url,
        placement=body.placement,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        target_institution_ids=body.target_institution_ids,
    )
    return ok(_to_ad_out(ad))


@ads_router.patch(
    "/advertisements/{ad_id}",
    response_model=Envelope[AdOut],
    summary="Update advertisement",
)
def update_advertisement(
    ad_id: uuid.UUID,
    body: AdIn,
    db: DbSession,
    principal: _RequireManage,
) -> Envelope[AdOut]:
    ad = service.update_advertisement(
        db,
        actor=principal,
        ad_id=ad_id,
        title=body.title,
        body=body.body,
        image_url=body.image_url,
        click_url=body.click_url,
        placement=body.placement,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        target_institution_ids=body.target_institution_ids,
    )
    return ok(_to_ad_out(ad))


@ads_router.post(
    "/advertisements/{ad_id}/status",
    response_model=Envelope[AdOut],
    summary="Change advertisement status",
)
def change_status(
    ad_id: uuid.UUID,
    body: AdStatusIn,
    db: DbSession,
    principal: _RequireManage,
    meta: RequestMetaDep,
) -> Envelope[AdOut]:
    ad = service.change_status(
        db,
        actor=principal,
        ad_id=ad_id,
        new_status=body.status,
        rejection_reason=body.rejection_reason,
        meta=meta,
    )
    return ok(_to_ad_out(ad))


@ads_router.get(
    "/advertisements/{ad_id}/metrics",
    response_model=Envelope[AdMetricsOut],
    summary="Ad metrics",
)
def ad_metrics(
    ad_id: uuid.UUID,
    db: DbSession,
    _principal: _RequireManage,
) -> Envelope[AdMetricsOut]:
    metrics = service.get_ad_metrics(db, ad_id=ad_id)
    return ok(AdMetricsOut(**metrics))


# ─── Platform analytics ───────────────────────────────────────────────────────


@analytics_router.get(
    "",
    response_model=Envelope[PlatformAnalyticsOut],
    summary="Platform-level analytics overview",
)
def platform_analytics(
    db: DbSession,
    principal: _RequireAnalytics,
) -> Envelope[PlatformAnalyticsOut]:
    from sqlalchemy import func, select

    from app.modules.printing.models import PrintOrder
    from app.modules.resources.models import Resource, ResourceStatus
    from app.modules.users.models import User

    principal.scope_for("analytics:read")

    def _count(model: type, **filters: object) -> int:
        q = select(func.count()).select_from(model)
        for col, val in filters.items():
            q = q.where(getattr(model, col) == val)
        return db.scalar(q) or 0

    users = _count(User)
    resources = _count(Resource)
    published = (
        db.scalar(select(func.count()).where(Resource.status == ResourceStatus.PUBLISHED)) or 0
    )
    orders = _count(PrintOrder)
    completed = db.scalar(select(func.count()).where(PrintOrder.status == "COMPLETED")) or 0
    ad_totals = service.get_platform_ad_totals(db)

    return ok(
        PlatformAnalyticsOut(
            total_users=users,
            total_resources=resources,
            published_resources=published,
            total_orders=orders,
            completed_orders=completed,
            total_impressions=ad_totals["impressions"],
            total_clicks=ad_totals["clicks"],
        )
    )


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _to_ad_out(ad: object) -> AdOut:
    from app.modules.advertising.models import Advertisement

    assert isinstance(ad, Advertisement)
    return AdOut(
        id=ad.id,
        campaign_id=ad.campaign_id,
        status=ad.status,
        title=ad.title,
        body=ad.body,
        image_url=ad.image_url,
        click_url=ad.click_url,
        placement=ad.placement,
        starts_at=ad.starts_at,
        ends_at=ad.ends_at,
        rejection_reason=ad.rejection_reason,
        target_institution_ids=[t.institution_id for t in ad.targets],
        created_at=ad.created_at,
        updated_at=ad.updated_at,
    )
