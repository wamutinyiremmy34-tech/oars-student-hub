"""Advertising service: lifecycle management, ad serving, impression/click recording, analytics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, NotFoundError
from app.modules.advertising.models import AdEvent, AdTarget, Advertisement, Advertiser, Campaign
from app.modules.audit import service as audit
from app.modules.rbac.principal import Principal

# ─────────────────────────────────────────────────────────────────────────────
# Advertiser management
# ─────────────────────────────────────────────────────────────────────────────


def create_advertiser(db: Session, *, name: str, contact_email: str) -> Advertiser:
    adv = Advertiser(name=name, contact_email=contact_email)
    db.add(adv)
    db.commit()
    return adv


def list_advertisers(db: Session) -> list[Advertiser]:
    return list(db.scalars(select(Advertiser).order_by(Advertiser.name)))


# ─────────────────────────────────────────────────────────────────────────────
# Campaign management
# ─────────────────────────────────────────────────────────────────────────────


def create_campaign(
    db: Session,
    *,
    advertiser_id: uuid.UUID,
    name: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
) -> Campaign:
    # Validate advertiser exists.
    if not db.get(Advertiser, advertiser_id):
        raise NotFoundError("Advertiser not found.")
    c = Campaign(advertiser_id=advertiser_id, name=name, starts_at=starts_at, ends_at=ends_at)
    db.add(c)
    db.commit()
    return c


def list_campaigns(db: Session, *, advertiser_id: uuid.UUID | None = None) -> list[Campaign]:
    q = select(Campaign).order_by(Campaign.created_at.desc())
    if advertiser_id:
        q = q.where(Campaign.advertiser_id == advertiser_id)
    return list(db.scalars(q))


def update_campaign(
    db: Session,
    *,
    campaign_id: uuid.UUID,
    name: str | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_active: bool | None = None,
) -> Campaign:
    c = db.get(Campaign, campaign_id)
    if c is None:
        raise NotFoundError("Campaign not found.")
    if name is not None:
        c.name = name
    if starts_at is not None:
        c.starts_at = starts_at
    if ends_at is not None:
        c.ends_at = ends_at
    if is_active is not None:
        c.is_active = is_active
    db.commit()
    return c


# ─────────────────────────────────────────────────────────────────────────────
# Advertisement lifecycle
# ─────────────────────────────────────────────────────────────────────────────

# Allowed transitions: current_status -> set of permitted next statuses.
_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"UNDER_REVIEW", "ARCHIVED"},
    "UNDER_REVIEW": {"ACTIVE", "SCHEDULED", "REJECTED", "ARCHIVED"},
    "SCHEDULED": {"ACTIVE", "PAUSED", "ARCHIVED"},
    "ACTIVE": {"PAUSED", "ARCHIVED"},
    "PAUSED": {"ACTIVE", "ARCHIVED"},
    "REJECTED": {"DRAFT"},
    "ARCHIVED": set(),
}


def create_advertisement(
    db: Session,
    *,
    actor: Principal,
    campaign_id: uuid.UUID,
    title: str,
    body: str | None,
    image_url: str | None,
    click_url: str | None,
    placement: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    target_institution_ids: list[uuid.UUID],
) -> Advertisement:
    actor.require("advertisement:manage")
    if not db.get(Campaign, campaign_id):
        raise NotFoundError("Campaign not found.")
    ad = Advertisement(
        campaign_id=campaign_id,
        status="DRAFT",
        title=title,
        body=body,
        image_url=image_url,
        click_url=click_url,
        placement=placement,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(ad)
    db.flush()
    _sync_targets(db, ad, target_institution_ids)
    db.commit()
    return _enrich(db, ad)


def update_advertisement(
    db: Session,
    *,
    actor: Principal,
    ad_id: uuid.UUID,
    **fields: Any,
) -> Advertisement:
    actor.require("advertisement:manage")
    ad = _get_or_404(db, ad_id)
    if ad.status not in ("DRAFT", "REJECTED"):
        raise BadRequestError(
            "Only DRAFT or REJECTED advertisements can be edited.", code="wrong_status"
        )
    for key, value in fields.items():
        if key == "target_institution_ids":
            _sync_targets(db, ad, value)
        elif hasattr(ad, key):
            setattr(ad, key, value)
    db.commit()
    return _enrich(db, ad)


def change_status(
    db: Session,
    *,
    actor: Principal,
    ad_id: uuid.UUID,
    new_status: str,
    rejection_reason: str | None = None,
    meta: Any = None,
) -> Advertisement:
    actor.require("advertisement:manage")
    ad = _get_or_404(db, ad_id)
    allowed = _TRANSITIONS.get(ad.status, set())
    if new_status not in allowed:
        raise BadRequestError(
            f"Cannot transition from {ad.status} to {new_status}.",
            code="invalid_transition",
        )
    if new_status == "REJECTED" and not rejection_reason:
        raise BadRequestError("A rejection reason is required.", code="reason_required")
    ad.status = new_status
    if new_status == "REJECTED":
        ad.rejection_reason = rejection_reason
    audit.record(
        db,
        action=f"advertisement.{new_status.lower()}",
        actor_user_id=actor.user.id,
        target_type="advertisement",
        target_id=str(ad.id),
        details={"from": ad.status, "to": new_status, "reason": rejection_reason},
        meta=meta,
    )
    db.commit()
    return _enrich(db, ad)


def list_advertisements(
    db: Session,
    *,
    campaign_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[Advertisement]:
    q = select(Advertisement).order_by(Advertisement.created_at.desc())
    if campaign_id:
        q = q.where(Advertisement.campaign_id == campaign_id)
    if status:
        q = q.where(Advertisement.status == status)
    ads = list(db.scalars(q))
    return [_enrich(db, ad) for ad in ads]


# ─────────────────────────────────────────────────────────────────────────────
# Ad serving
# ─────────────────────────────────────────────────────────────────────────────


def get_active_ads(
    db: Session,
    *,
    placement: str,
    institution_id: uuid.UUID | None = None,
    limit: int = 3,
) -> list[Advertisement]:
    """Return ACTIVE advertisements eligible for *placement* and *institution*.

    Only ads whose schedule is current are returned.  Targeting: an ad with no
    targets (platform-wide) is always eligible; an ad with targets is only eligible
    if one target matches the requested institution.
    """
    now = datetime.now(UTC)
    q = (
        select(Advertisement)
        .where(
            Advertisement.status == "ACTIVE",
            Advertisement.placement == placement,
            # Respect schedule: start_at must be past (or unset), end_at must be future (or unset).
            (Advertisement.starts_at.is_(None)) | (Advertisement.starts_at <= now),
            (Advertisement.ends_at.is_(None)) | (Advertisement.ends_at > now),
        )
        .order_by(func.random())
        .limit(limit)
    )
    candidates = list(db.scalars(q))
    result = []
    for ad in candidates:
        if _is_targeted(db, ad, institution_id):
            result.append(ad)
    return result


def _is_targeted(db: Session, ad: Advertisement, institution_id: uuid.UUID | None) -> bool:
    targets = list(db.scalars(select(AdTarget).where(AdTarget.advertisement_id == ad.id)))
    if not targets:
        return True  # platform-wide
    if institution_id is None:
        return False  # institution-specific ads need a context
    return any(t.institution_id == institution_id or t.institution_id is None for t in targets)


# ─────────────────────────────────────────────────────────────────────────────
# Event recording
# ─────────────────────────────────────────────────────────────────────────────


def record_event(
    db: Session,
    *,
    ad_id: uuid.UUID,
    event_type: str,
    institution_id: uuid.UUID | None,
    session_token: str | None,
) -> None:
    """Record an impression or click.  Silently ignores unknown ad IDs to prevent error leakage."""
    if event_type not in ("IMPRESSION", "CLICK"):
        raise BadRequestError("event_type must be IMPRESSION or CLICK", code="invalid_event_type")
    ad = db.get(Advertisement, ad_id)
    if ad is None or ad.status != "ACTIVE":
        return  # silently ignore — don't expose whether an ad exists
    event = AdEvent(
        advertisement_id=ad_id,
        event_type=event_type,
        institution_id=institution_id,
        session_token=session_token,
    )
    db.add(event)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────


def get_ad_metrics(db: Session, *, ad_id: uuid.UUID) -> dict[str, int]:
    impressions = (
        db.scalar(
            select(func.count()).where(
                AdEvent.advertisement_id == ad_id, AdEvent.event_type == "IMPRESSION"
            )
        )
        or 0
    )
    clicks = (
        db.scalar(
            select(func.count()).where(
                AdEvent.advertisement_id == ad_id, AdEvent.event_type == "CLICK"
            )
        )
        or 0
    )
    return {"advertisement_id": str(ad_id), "impressions": impressions, "clicks": clicks}


def get_platform_ad_totals(db: Session) -> dict[str, int]:
    impressions = db.scalar(select(func.count()).where(AdEvent.event_type == "IMPRESSION")) or 0
    clicks = db.scalar(select(func.count()).where(AdEvent.event_type == "CLICK")) or 0
    return {"impressions": impressions, "clicks": clicks}


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_or_404(db: Session, ad_id: uuid.UUID) -> Advertisement:
    ad = db.get(Advertisement, ad_id)
    if ad is None:
        raise NotFoundError("Advertisement not found.")
    return ad


def _sync_targets(db: Session, ad: Advertisement, institution_ids: list[uuid.UUID]) -> None:
    """Replace ad targets with the given institution list."""
    existing = list(db.scalars(select(AdTarget).where(AdTarget.advertisement_id == ad.id)))
    for t in existing:
        db.delete(t)
    db.flush()
    for inst_id in institution_ids:
        db.add(AdTarget(advertisement_id=ad.id, institution_id=inst_id))
    db.flush()


def _enrich(db: Session, ad: Advertisement) -> Advertisement:
    """Eagerly load targets so callers can access ad.targets without lazy loading."""
    db.refresh(ad)
    return ad
