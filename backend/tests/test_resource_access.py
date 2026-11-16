"""Who can download what: free vs premium, entitlements, unpublished content, signed links."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import PDF, Campus, auth_headers, make_resource, v1
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_download_token, decode_download_token
from app.modules.files.models import StoredFile
from app.modules.resources.models import ResourceDownload, ResourceVersion

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> Campus:
    return Campus(db)


def download(client: TestClient, user, rid):  # type: ignore[no-untyped-def]
    headers = auth_headers(user) if user is not None else {}
    return client.post(v1(f"/resources/{rid}/download"), headers=headers)


def grant(client: TestClient, admin, rid, user, **extra):  # type: ignore[no-untyped-def]
    return client.post(
        v1(f"/resources/{rid}/entitlements"),
        json={"user_id": str(user.id), **extra},
        headers=auth_headers(admin),
    )


# --------------------------------------------------------------------------- free resources


def test_anonymous_users_can_see_metadata_but_not_download(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db,
        provider=campus.provider,
        institution=campus.inst_a,
        storage=storage,
        status="PUBLISHED",
        title="Open notes",
    )
    detail = api_client.get(v1(f"/resources/{resource.id}"))
    assert detail.status_code == 200
    assert detail.json()["data"]["viewer"]["download_block_reason"] == "authentication_required"
    assert "resources/test" not in detail.text  # the storage key is never exposed
    assert download(api_client, None, resource.id).status_code == 401


def test_free_download_returns_a_short_lived_link_that_streams_the_file(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="PUBLISHED"
    )
    response = download(api_client, campus.student, resource.id)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["delivery"] == "STREAM" and data["expires_in"] == 60
    assert data["url"].startswith("/api/v1/downloads/")
    assert "resources/test" not in response.text

    file_response = api_client.get(data["url"])  # the link itself needs no Authorization header
    assert file_response.status_code == 200
    assert file_response.content == PDF
    assert file_response.headers["content-type"] == "application/pdf"
    assert "attachment" in file_response.headers["content-disposition"]
    assert file_response.headers["x-content-type-options"] == "nosniff"

    logged = db.scalars(
        select(ResourceDownload).where(ResourceDownload.resource_id == resource.id)
    ).all()
    assert [(d.user_id, d.delivery) for d in logged] == [(campus.student.id, "STREAM")]


def test_published_resource_serves_its_current_version(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    from helpers import put_file

    resource = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="PUBLISHED"
    )
    current = db.scalar(select(ResourceVersion).where(ResourceVersion.resource_id == resource.id))
    newer = put_file(db, storage, campus.provider)
    db.add(
        ResourceVersion(
            resource_id=resource.id,
            version_number=2,
            file_id=newer.id,
            is_current=False,
            created_by_user_id=campus.provider.id,
        )
    )
    db.commit()

    url = download(api_client, campus.student, resource.id).json()["data"]["url"]
    assert decode_download_token(url.rsplit("/", 1)[1])["fid"] == str(
        current.file_id
    )  # not the newer, unpublished one


# --------------------------------------------------------------------------- premium


def test_premium_requires_an_entitlement_and_the_backend_decides(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    c = campus
    resource = make_resource(
        db,
        provider=c.provider,
        institution=c.inst_a,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
        price=5000,
    )

    denied = download(api_client, c.student, resource.id)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "premium_required"
    view = api_client.get(v1(f"/resources/{resource.id}"), headers=auth_headers(c.student)).json()[
        "data"
    ]
    assert (
        view["viewer"]["can_download"] is False
        and view["viewer"]["download_block_reason"] == "premium_required"
    )
    assert view["price_ugx"] == 5000  # the price and preview are public; the file is not
    assert (
        db.scalar(select(func.count()).select_from(ResourceDownload)) == 0
    )  # nothing logged for a refusal

    assert grant(api_client, c.admin_a, resource.id, c.student).status_code == 201
    allowed = download(api_client, c.student, resource.id)
    assert allowed.status_code == 200
    assert api_client.get(allowed.json()["data"]["url"]).content == PDF
    assert (
        download(api_client, c.student2, resource.id).status_code == 403
    )  # entitlements are per user

    revoked = api_client.delete(
        v1(f"/resources/{resource.id}/entitlements/{c.student.id}"), headers=auth_headers(c.admin_a)
    )
    assert revoked.status_code == 200
    assert download(api_client, c.student, resource.id).status_code == 403

    assert (
        grant(api_client, c.admin_a, resource.id, c.student).status_code == 201
    )  # re-grant reactivates the same row
    assert download(api_client, c.student, resource.id).status_code == 200


def test_expired_entitlements_do_not_grant_access(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db,
        provider=campus.provider,
        institution=campus.inst_a,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
    )
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert (
        grant(api_client, campus.admin_a, resource.id, campus.student, expires_at=past).status_code
        == 201
    )
    assert download(api_client, campus.student, resource.id).status_code == 403


def test_only_authorised_staff_can_grant_entitlements(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    c = campus
    premium = make_resource(
        db,
        provider=c.provider,
        institution=c.inst_a,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
    )
    free = make_resource(
        db, provider=c.provider, institution=c.inst_a, storage=storage, status="PUBLISHED"
    )

    assert (
        grant(api_client, c.student, premium.id, c.student).status_code == 403
    )  # cannot grant yourself access
    assert (
        grant(api_client, c.provider, premium.id, c.student).status_code == 403
    )  # providers cannot either
    assert (
        grant(api_client, c.admin_b, premium.id, c.student).status_code == 404
    )  # other university's admin
    assert (
        grant(api_client, c.admin_a, free.id, c.student).status_code == 409
    )  # only premium uses entitlements
    unknown = api_client.post(
        v1(f"/resources/{premium.id}/entitlements"),
        json={"user_id": "00000000-0000-0000-0000-000000000009"},
        headers=auth_headers(c.admin_a),
    )
    assert unknown.status_code == 404
    assert grant(api_client, c.platform, premium.id, c.student).status_code == 201
    assert download(api_client, c.student, premium.id).status_code == 200


def test_owner_and_scoped_staff_override_the_premium_check(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    c = campus
    resource = make_resource(
        db,
        provider=c.provider,
        institution=c.inst_a,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
    )
    assert download(api_client, c.provider, resource.id).status_code == 200
    assert download(api_client, c.admin_a, resource.id).status_code == 200
    assert (
        download(api_client, c.admin_b, resource.id).status_code == 403
    )  # other institution's staff: just a visitor
    assert download(api_client, c.provider2, resource.id).status_code == 403


# --------------------------------------------------------------------------- unpublished content


@pytest.mark.parametrize(
    "status", ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "ARCHIVED"]
)
def test_unpublished_resources_cannot_be_downloaded_by_the_public(
    api_client: TestClient, campus: Campus, db: Session, storage, status: str
) -> None:  # type: ignore[no-untyped-def]
    c = campus
    resource = make_resource(
        db, provider=c.provider, institution=c.inst_a, storage=storage, status=status
    )
    for outsider in (c.student, c.provider2, c.admin_b):
        assert download(api_client, outsider, resource.id).status_code == 404
    assert api_client.get(v1(f"/resources/{resource.id}")).status_code == 404
    # ...but the owner and in-scope staff can (the reviewer needs the file to review it)
    assert download(api_client, c.provider, resource.id).status_code == 200
    assert download(api_client, c.admin_a, resource.id).status_code == 200


def test_unknown_resource_and_resource_without_a_file(
    api_client: TestClient, campus: Campus, db: Session
) -> None:
    c = campus
    assert (
        download(api_client, c.student, "00000000-0000-0000-0000-000000000042").status_code == 404
    )
    empty = make_resource(
        db, provider=c.provider, institution=c.inst_a, status="PUBLISHED", with_file=False
    )
    response = download(api_client, c.student, empty.id)
    assert response.status_code == 404 and response.json()["error"]["code"] == "no_file"


# --------------------------------------------------------------------------- the signed link


def test_download_links_are_scoped_short_lived_and_not_interchangeable(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    c = campus
    resource = make_resource(
        db, provider=c.provider, institution=c.inst_a, storage=storage, status="PUBLISHED"
    )
    file_id = db.scalar(select(StoredFile.id).limit(1))

    assert api_client.get(v1("/downloads/garbage")).status_code == 401
    expired = create_download_token(user_id=str(c.student.id), file_id=str(file_id), ttl_seconds=-5)
    assert api_client.get(v1(f"/downloads/{expired}")).status_code == 401
    assert (
        api_client.get(v1(f"/downloads/{create_access_token(str(c.student.id))}")).status_code
        == 401
    )  # an access token is not a link

    link = download(api_client, c.student, resource.id).json()["data"]["url"]
    c.student.status = "SUSPENDED"
    db.commit()
    assert api_client.get(link).status_code == 401  # suspended after the link was issued


def test_infected_files_are_never_served(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="PUBLISHED"
    )
    link = download(api_client, campus.student, resource.id).json()["data"]["url"]
    stored = db.scalar(select(StoredFile))
    stored.scan_status = "INFECTED"
    db.commit()

    blocked = download(api_client, campus.student, resource.id)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "file_unavailable"
    assert api_client.get(link).status_code == 404  # even an already-issued link stops working
