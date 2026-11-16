"""Advertising tests: lifecycle, targeting, event recording, analytics, authorization.

These are integration tests: they require a running PostgreSQL (docker compose up -d).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import auth_headers, make_institution, make_user
from sqlalchemy.orm import Session

from app.modules.advertising import service as ad_service
from app.modules.advertising.models import Advertisement, Advertiser, Campaign

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- helpers


def make_advertiser_and_campaign(db: Session) -> tuple[Advertiser, Campaign]:
    adv = ad_service.create_advertiser(db, name="Test Co", contact_email="ads@test.example")
    campaign = ad_service.create_campaign(
        db, advertiser_id=adv.id, name="Back to School", starts_at=None, ends_at=None
    )
    return adv, campaign


def make_ad(
    db: Session,
    *,
    actor,
    campaign_id: uuid.UUID,
    status: str = "DRAFT",
    placement: str = "dashboard_banner",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    target_institution_ids: list[uuid.UUID] | None = None,
) -> Advertisement:
    ad = ad_service.create_advertisement(
        db,
        actor=actor,
        campaign_id=campaign_id,
        title="Special Offer",
        body="50% off printing",
        image_url=None,
        click_url="https://shop.example",
        placement=placement,
        starts_at=starts_at,
        ends_at=ends_at,
        target_institution_ids=target_institution_ids or [],
    )
    if status != "DRAFT":
        ad_service.change_status(db, actor=actor, ad_id=ad.id, new_status="UNDER_REVIEW")
        ad = ad_service.change_status(db, actor=actor, ad_id=ad.id, new_status=status)
    return ad


# --------------------------------------------------------------------------- authorization


def test_ad_management_requires_permission(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    student = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])
    admin = make_user(db, roles=[("ADMIN", None)])

    adv = ad_service.create_advertiser(db, name="Test Co", contact_email="ads@test.example")
    campaign = ad_service.create_campaign(
        db, advertiser_id=adv.id, name="Campaign", starts_at=None, ends_at=None
    )

    # Student cannot create an advertisement.
    response = api_client.post(
        "/api/v1/ads/advertisements",
        json={
            "campaign_id": str(campaign.id),
            "title": "Ad",
            "body": "Body",
            "image_url": None,
            "click_url": None,
            "placement": "dashboard_banner",
            "starts_at": None,
            "ends_at": None,
            "target_institution_ids": [],
        },
        headers=auth_headers(student),
    )
    assert response.status_code == 403

    # Admin can.
    response = api_client.post(
        "/api/v1/ads/advertisements",
        json={
            "campaign_id": str(campaign.id),
            "title": "Ad",
            "body": "Body",
            "image_url": None,
            "click_url": None,
            "placement": "dashboard_banner",
            "starts_at": None,
            "ends_at": None,
            "target_institution_ids": [],
        },
        headers=auth_headers(admin),
    )
    assert response.status_code == 201


def test_ad_serving_is_public(api_client: TestClient, db: Session) -> None:
    """Anyone (even unauthenticated) can fetch ads to display."""
    response = api_client.get("/api/v1/ads?placement=dashboard_banner")
    assert response.status_code == 200


# --------------------------------------------------------------------------- lifecycle transitions


def test_ad_lifecycle_transitions(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)

    ad = make_ad(db, actor=admin, campaign_id=campaign.id)
    assert ad.status == "DRAFT"

    # DRAFT → UNDER_REVIEW → ACTIVE → PAUSED → ACTIVE → ARCHIVED
    ad = ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="UNDER_REVIEW")
    assert ad.status == "UNDER_REVIEW"

    ad = ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="ACTIVE")
    assert ad.status == "ACTIVE"

    ad = ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="PAUSED")
    assert ad.status == "PAUSED"

    ad = ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="ACTIVE")
    assert ad.status == "ACTIVE"

    ad = ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="ARCHIVED")
    assert ad.status == "ARCHIVED"


def test_invalid_transition_is_rejected(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)

    ad = make_ad(db, actor=admin, campaign_id=campaign.id)
    # DRAFT → ACTIVE is not allowed (must go through UNDER_REVIEW first).
    with pytest.raises(Exception, match="invalid_transition"):
        ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="ACTIVE")


def test_rejection_requires_a_reason(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)

    ad = make_ad(db, actor=admin, campaign_id=campaign.id)
    ad = ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="UNDER_REVIEW")

    # Rejection without a reason must fail.
    with pytest.raises(Exception, match="reason_required"):
        ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="REJECTED")

    # With a reason it works.
    ad = ad_service.change_status(
        db, actor=admin, ad_id=ad.id, new_status="REJECTED", rejection_reason="Misleading content"
    )
    assert ad.status == "REJECTED"
    assert ad.rejection_reason == "Misleading content"


def test_only_draft_or_rejected_ads_can_be_edited(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)

    ad = make_ad(db, actor=admin, campaign_id=campaign.id)
    # Move to ACTIVE — editing should now be rejected.
    ad = ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="UNDER_REVIEW")
    ad = ad_service.change_status(db, actor=admin, ad_id=ad.id, new_status="ACTIVE")

    with pytest.raises(Exception, match="wrong_status"):
        ad_service.update_advertisement(
            db,
            actor=admin,
            ad_id=ad.id,
            title="Changed Title",
            body="x",
            image_url=None,
            click_url=None,
            placement="dashboard_banner",
            starts_at=None,
            ends_at=None,
            target_institution_ids=[],
        )


# --------------------------------------------------------------------------- scheduling and expiry


def test_active_ad_with_future_start_is_not_served(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)

    future = datetime.now(UTC) + timedelta(hours=1)
    ad = make_ad(db, actor=admin, campaign_id=campaign.id, status="ACTIVE", starts_at=future)
    assert ad.status == "ACTIVE"

    ads = ad_service.get_active_ads(db, placement="dashboard_banner")
    assert ad.id not in {a.id for a in ads}  # scheduled for the future, not served yet


def test_active_ad_with_past_end_is_not_served(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)

    past = datetime.now(UTC) - timedelta(hours=1)
    ad = make_ad(db, actor=admin, campaign_id=campaign.id, status="ACTIVE", ends_at=past)

    ads = ad_service.get_active_ads(db, placement="dashboard_banner")
    assert ad.id not in {a.id for a in ads}


def test_active_ad_with_current_schedule_is_served(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)

    now = datetime.now(UTC)
    ad = make_ad(
        db,
        actor=admin,
        campaign_id=campaign.id,
        status="ACTIVE",
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
    )

    ads = ad_service.get_active_ads(db, placement="dashboard_banner")
    assert ad.id in {a.id for a in ads}


# --------------------------------------------------------------------------- targeting


def test_platform_wide_ad_served_to_all_institutions(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    inst_a = make_institution(db)
    inst_b = make_institution(db)
    _, campaign = make_advertiser_and_campaign(db)

    ad = make_ad(
        db, actor=admin, campaign_id=campaign.id, status="ACTIVE", target_institution_ids=[]
    )

    # No institution context.
    ads = ad_service.get_active_ads(db, placement="dashboard_banner", institution_id=None)
    assert ad.id in {a.id for a in ads}

    # Institution A.
    ads = ad_service.get_active_ads(db, placement="dashboard_banner", institution_id=inst_a.id)
    assert ad.id in {a.id for a in ads}

    # Institution B.
    ads = ad_service.get_active_ads(db, placement="dashboard_banner", institution_id=inst_b.id)
    assert ad.id in {a.id for a in ads}


def test_institution_targeted_ad_only_served_to_matching_institution(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    inst_a = make_institution(db)
    inst_b = make_institution(db)
    _, campaign = make_advertiser_and_campaign(db)

    ad = make_ad(
        db,
        actor=admin,
        campaign_id=campaign.id,
        status="ACTIVE",
        target_institution_ids=[inst_a.id],
    )

    # Served to institution A.
    ads = ad_service.get_active_ads(db, placement="dashboard_banner", institution_id=inst_a.id)
    assert ad.id in {a.id for a in ads}

    # NOT served to institution B.
    ads = ad_service.get_active_ads(db, placement="dashboard_banner", institution_id=inst_b.id)
    assert ad.id not in {a.id for a in ads}

    # NOT served without an institution context.
    ads = ad_service.get_active_ads(db, placement="dashboard_banner", institution_id=None)
    assert ad.id not in {a.id for a in ads}


# --------------------------------------------------------------------------- event recording


def test_impression_and_click_are_recorded(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)
    ad = make_ad(db, actor=admin, campaign_id=campaign.id, status="ACTIVE")

    ad_service.record_event(
        db, ad_id=ad.id, event_type="IMPRESSION", institution_id=None, session_token="sess-1"
    )
    ad_service.record_event(
        db, ad_id=ad.id, event_type="CLICK", institution_id=None, session_token="sess-1"
    )

    metrics = ad_service.get_ad_metrics(db, ad_id=ad.id)
    assert metrics["impressions"] == 1
    assert metrics["clicks"] == 1


def test_event_recording_silently_ignores_unknown_ad(db: Session) -> None:
    """Recording an event for a non-existent ad must not raise."""
    ad_service.record_event(
        db, ad_id=uuid.uuid4(), event_type="IMPRESSION", institution_id=None, session_token="s"
    )
    # No exception, no events created.


def test_invalid_event_type_is_rejected(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)
    ad = make_ad(db, actor=admin, campaign_id=campaign.id, status="ACTIVE")

    with pytest.raises(Exception, match="invalid_event_type"):
        ad_service.record_event(
            db, ad_id=ad.id, event_type="INVALID", institution_id=None, session_token="s"
        )


# --------------------------------------------------------------------------- analytics


def test_platform_ad_totals(db: Session) -> None:
    admin = make_user(db, roles=[("ADMIN", None)])
    _, campaign = make_advertiser_and_campaign(db)
    ad = make_ad(db, actor=admin, campaign_id=campaign.id, status="ACTIVE")

    for _ in range(3):
        ad_service.record_event(
            db, ad_id=ad.id, event_type="IMPRESSION", institution_id=None, session_token="s"
        )
    for _ in range(2):
        ad_service.record_event(
            db, ad_id=ad.id, event_type="CLICK", institution_id=None, session_token="s"
        )

    totals = ad_service.get_platform_ad_totals(db)
    assert totals["impressions"] >= 3
    assert totals["clicks"] >= 2


def test_analytics_endpoint_requires_permission(api_client: TestClient, db: Session) -> None:
    institution = make_institution(db)
    student = make_user(db, institution=institution, roles=[("STUDENT", institution.id)])
    admin = make_user(db, roles=[("ADMIN", None)])

    assert api_client.get("/api/v1/analytics", headers=auth_headers(student)).status_code == 403
    assert api_client.get("/api/v1/analytics", headers=auth_headers(admin)).status_code == 200
