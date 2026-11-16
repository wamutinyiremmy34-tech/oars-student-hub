"""Resource CRUD, versions and the moderation lifecycle, with object-level and institution-scope checks."""

import pytest
from fastapi.testclient import TestClient
from helpers import PDF, Campus, auth_headers, make_resource, make_user, override_db, v1
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.audit.models import AuditLog
from app.modules.files.models import StoredFile
from app.modules.rbac.models import Permission, Role, RolePermission
from app.modules.rbac.service import add_user_role
from app.modules.resources.models import Resource, ResourceReview, ResourceVersion

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> Campus:
    return Campus(db)


def create(client: TestClient, user, payload):  # type: ignore[no-untyped-def]
    return client.post(v1("/resources"), json=payload, headers=auth_headers(user))


def upload(client: TestClient, user, rid, content: bytes = PDF, name: str = "notes.pdf"):  # type: ignore[no-untyped-def]
    return client.post(
        v1(f"/resources/{rid}/versions"),
        files={"file": (name, content, "application/pdf")},
        data={"changelog": "update"},
        headers=auth_headers(user),
    )


def act(client: TestClient, user, rid, action: str, body=None):  # type: ignore[no-untyped-def]
    return client.post(v1(f"/resources/{rid}/{action}"), json=body, headers=auth_headers(user))


def publish_via_api(client: TestClient, c: Campus) -> str:
    rid = create(client, c.provider, c.create_payload()).json()["data"]["id"]
    assert upload(client, c.provider, rid).status_code == 201
    assert act(client, c.provider, rid, "submit").status_code == 200
    assert act(client, c.admin_a, rid, "start-review").status_code == 200
    assert act(client, c.admin_a, rid, "approve", {}).status_code == 200
    assert act(client, c.admin_a, rid, "publish").status_code == 200
    return rid


# --------------------------------------------------------------------------- creation


def test_provider_creates_a_draft_with_normalised_tags_and_course_links(
    api_client: TestClient, campus: Campus
) -> None:
    response = create(api_client, campus.provider, campus.create_payload())
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "DRAFT"
    assert data["tags"] == ["calculus", "math"]  # lower-cased and de-duplicated
    assert [c["code"] for c in data["courses"]] == ["MTH1101"]
    assert data["viewer"]["is_owner"] is True
    assert data["price_ugx"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"access_type": "PREMIUM"},  # premium needs a price
        {"access_type": "FREE", "price_ugx": 1000},  # free must not have one
        {"access_type": "PREMIUM", "price_ugx": 0},
        {"access_type": "PREMIUM", "price_ugx": 12.5},  # money is integer UGX
        {"title": "ab"},
        {"tags": ["bad tag!"]},
    ],
)
def test_invalid_resource_payloads_are_rejected(
    api_client: TestClient, campus: Campus, overrides: dict[str, object]
) -> None:
    assert (
        create(api_client, campus.provider, campus.create_payload(**overrides)).status_code == 422
    )


def test_creation_rules_for_scope_course_category_and_role(
    api_client: TestClient, campus: Campus
) -> None:
    other_course = create(
        api_client,
        campus.provider,
        campus.create_payload(course_ids=[str(campus.tree_b.course.id)]),
    )
    assert other_course.status_code == 400
    assert other_course.json()["error"]["code"] == "invalid_course"

    bad_category = create(
        api_client,
        campus.provider,
        campus.create_payload(category_id="00000000-0000-0000-0000-000000000001"),
    )
    assert bad_category.json()["error"]["code"] == "invalid_category"

    # A provider for university A cannot publish into university B.
    wrong_institution = create(
        api_client,
        campus.provider,
        campus.create_payload(institution_id=str(campus.inst_b.id), course_ids=[]),
    )
    assert wrong_institution.status_code == 403

    assert create(api_client, campus.student, campus.create_payload()).status_code == 403
    assert api_client.post(v1("/resources"), json=campus.create_payload()).status_code == 401


# --------------------------------------------------------------------------- visibility and ownership


def test_drafts_are_private_to_the_owner_and_in_scope_reviewers(
    api_client: TestClient, campus: Campus
) -> None:
    rid = create(api_client, campus.provider, campus.create_payload()).json()["data"]["id"]
    url = v1(f"/resources/{rid}")

    assert api_client.get(url, headers=auth_headers(campus.provider)).status_code == 200
    assert api_client.get(url, headers=auth_headers(campus.admin_a)).status_code == 200
    assert api_client.get(url, headers=auth_headers(campus.platform)).status_code == 200
    for outsider in (campus.student, campus.provider2, campus.admin_b, campus.provider_b):
        assert api_client.get(url, headers=auth_headers(outsider)).status_code == 404
    assert api_client.get(url).status_code == 404  # anonymous


def test_only_the_owner_can_edit_and_upload(api_client: TestClient, campus: Campus) -> None:
    rid = create(api_client, campus.provider, campus.create_payload()).json()["data"]["id"]
    patch = lambda user: api_client.patch(
        v1(f"/resources/{rid}"), json={"title": "Hacked title"}, headers=auth_headers(user)
    )  # noqa: E731

    assert patch(campus.provider).status_code == 200
    assert patch(campus.provider2).status_code == 404  # another provider cannot even see the draft
    assert patch(campus.student).status_code == 403
    assert (
        patch(campus.admin_a).status_code == 403
    )  # staff can see it but may not edit someone else's work
    assert upload(api_client, campus.provider2, rid).status_code == 404
    assert (
        api_client.get(v1(f"/resources/{rid}"), headers=auth_headers(campus.provider)).json()[
            "data"
        ]["title"]
        == "Hacked title"
    )


def test_other_providers_get_403_on_a_published_resource(
    api_client: TestClient, campus: Campus
) -> None:
    rid = publish_via_api(api_client, campus)
    response = api_client.patch(
        v1(f"/resources/{rid}"), json={"title": "x" * 5}, headers=auth_headers(campus.provider2)
    )
    assert response.status_code == 403  # visible to them, but not theirs


# --------------------------------------------------------------------------- versions and uploads


def test_versions_are_numbered_and_history_is_kept(
    api_client: TestClient, campus: Campus, db: Session
) -> None:
    rid = create(api_client, campus.provider, campus.create_payload()).json()["data"]["id"]
    first, second = (
        upload(api_client, campus.provider, rid),
        upload(api_client, campus.provider, rid),
    )
    assert (first.status_code, second.status_code) == (201, 201)
    assert [first.json()["data"]["version_number"], second.json()["data"]["version_number"]] == [
        1,
        2,
    ]
    assert first.json()["data"]["filename"] == "notes.pdf"
    assert "storage" not in first.text.lower() and "resources/" not in first.text
    assert db.scalar(select(func.count()).select_from(ResourceVersion)) == 2


def test_uploads_are_validated_by_content(
    api_client: TestClient, campus: Campus, db: Session
) -> None:
    rid = create(api_client, campus.provider, campus.create_payload()).json()["data"]["id"]
    exe = upload(
        api_client, campus.provider, rid, b"MZ" + b"\x00" * 200, name="notes.pdf"
    )  # .pdf name, exe content
    assert exe.status_code == 415
    assert exe.json()["error"]["code"] == "unsupported_file_type"
    html = upload(
        api_client, campus.provider, rid, b"<html><script>1</script></html>", name="page.pdf"
    )
    assert html.status_code == 415
    empty = upload(api_client, campus.provider, rid, b"")
    assert empty.status_code == 400
    assert (
        db.scalar(select(func.count()).select_from(StoredFile)) == 0
    )  # nothing rejected was stored


def test_oversized_uploads_are_rejected(
    db: Session, campus: Campus, storage, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient as Client

    from app.main import create_app

    monkeypatch.setenv("MAX_UPLOAD_BYTES", "2048")
    get_settings.cache_clear()
    app = create_app()
    override_db(app, db)
    app.state.storage = storage
    with Client(app) as client:
        rid = create(client, campus.provider, campus.create_payload()).json()["data"]["id"]
        response = upload(client, campus.provider, rid, PDF + b"0" * 5000)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


# --------------------------------------------------------------------------- lifecycle


def test_full_lifecycle_with_rejection_and_resubmission(
    api_client: TestClient, campus: Campus, db: Session
) -> None:
    c, client = campus, api_client
    rid = create(client, c.provider, c.create_payload()).json()["data"]["id"]

    no_file = act(client, c.provider, rid, "submit")
    assert no_file.status_code == 400 and no_file.json()["error"]["code"] == "no_file"

    upload(client, c.provider, rid)
    assert act(client, c.provider, rid, "submit").json()["data"]["status"] == "SUBMITTED"
    assert (
        client.patch(
            v1(f"/resources/{rid}"), json={"title": "Sneaky edit"}, headers=auth_headers(c.provider)
        ).status_code
        == 409
    )

    assert act(client, c.admin_a, rid, "start-review").json()["data"]["status"] == "UNDER_REVIEW"
    assert (
        act(client, c.admin_a, rid, "reject", {"reason": "x"}).status_code == 422
    )  # reason is mandatory
    rejected = act(
        client, c.admin_a, rid, "reject", {"reason": "Scan is unreadable, please re-upload."}
    )
    assert rejected.json()["data"]["status"] == "REJECTED"

    seen_by_owner = client.get(v1(f"/resources/{rid}"), headers=auth_headers(c.provider)).json()[
        "data"
    ]
    assert seen_by_owner["latest_review"]["reason"] == "Scan is unreadable, please re-upload."

    assert upload(client, c.provider, rid).status_code == 201  # editing/uploading reopens it
    assert (
        client.get(v1(f"/resources/{rid}"), headers=auth_headers(c.provider)).json()["data"][
            "status"
        ]
        == "DRAFT"
    )
    act(client, c.provider, rid, "submit")
    act(client, c.admin_a, rid, "start-review")
    assert (
        act(client, c.admin_a, rid, "approve", {"note": "Looks good"}).json()["data"]["status"]
        == "APPROVED"
    )
    published = act(client, c.admin_a, rid, "publish").json()["data"]
    assert published["status"] == "PUBLISHED" and published["published_at"]

    # public can now read it, and the decisions and reasons are all stored
    assert client.get(v1(f"/resources/{rid}")).status_code == 200
    decisions = list(
        db.scalars(
            select(ResourceReview.decision)
            .where(ResourceReview.resource_id == rid)
            .order_by(ResourceReview.created_at)
        )
    )
    assert decisions == [
        "SUBMITTED",
        "STARTED",
        "REJECTED",
        "SUBMITTED",
        "STARTED",
        "APPROVED",
        "PUBLISHED",
    ]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "resource.rejected")) is not None


def test_publish_marks_exactly_one_current_version(
    api_client: TestClient, campus: Campus, db: Session
) -> None:
    c, client = campus, api_client
    rid = create(client, c.provider, c.create_payload()).json()["data"]["id"]
    upload(client, c.provider, rid)
    upload(client, c.provider, rid)
    act(client, c.provider, rid, "submit")
    act(client, c.admin_a, rid, "start-review")
    act(client, c.admin_a, rid, "approve", {})
    detail = act(client, c.admin_a, rid, "publish").json()["data"]

    assert [(v["version_number"], v["is_current"]) for v in detail["versions"]] == [
        (2, True),
        (1, False),
    ]
    assert (
        db.scalar(
            select(func.count())
            .select_from(ResourceVersion)
            .where(ResourceVersion.is_current.is_(True))
        )
        == 1
    )
    public = client.get(v1(f"/resources/{rid}")).json()["data"]
    assert public["versions"] == []  # the public never sees version history
    assert public["file"]["version_number"] == 2


def test_invalid_transitions_are_refused(api_client: TestClient, campus: Campus) -> None:
    c, client = campus, api_client
    rid = create(client, c.provider, c.create_payload()).json()["data"]["id"]
    upload(client, c.provider, rid)
    assert act(client, c.admin_a, rid, "approve", {}).status_code == 409  # DRAFT cannot be approved
    act(client, c.provider, rid, "submit")
    assert (
        act(client, c.admin_a, rid, "publish").status_code == 409
    )  # SUBMITTED cannot be published
    assert act(client, c.provider, rid, "submit").status_code == 409  # already submitted
    assert (
        act(client, c.provider, rid, "publish").status_code == 403
    )  # provider lacks resource:publish


# --------------------------------------------------------------------------- separation of duties and scope


def test_nobody_moderates_their_own_resource_by_default(
    api_client: TestClient, campus: Campus, db: Session
) -> None:
    c, client = campus, api_client
    both = make_user(db, roles=[("RESOURCE_PROVIDER", c.inst_a.id), ("ADMIN", c.inst_a.id)])
    rid = create(client, both, c.create_payload()).json()["data"]["id"]
    upload(client, both, rid)
    act(client, both, rid, "submit")

    blocked = act(client, both, rid, "start-review")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "cannot_review_own"
    detail = client.get(v1(f"/resources/{rid}"), headers=auth_headers(both)).json()["data"]
    assert detail["viewer"]["can_review"] is False

    # Only an explicit, separate permission lifts the rule (no default role holds it).
    role = Role(name="SELF_REVIEWER", description="test", is_system=False)
    db.add(role)
    db.flush()
    permission = db.scalar(select(Permission).where(Permission.code == "resource:review_own"))
    assert permission is not None
    db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    add_user_role(db, user_id=both.id, role=role, institution_id=c.inst_a.id, granted_by=None)
    db.commit()
    assert act(client, both, rid, "start-review").status_code == 200


def test_scoped_admin_cannot_moderate_another_institutions_resources(
    api_client: TestClient, campus: Campus, db: Session
) -> None:
    c, client = campus, api_client
    resource = make_resource(
        db,
        provider=c.provider,
        institution=c.inst_a,
        status="SUBMITTED",
        storage=api_client.app.state.storage,
    )
    url = lambda action: v1(f"/resources/{resource.id}/{action}")  # noqa: E731

    assert client.post(url("start-review"), headers=auth_headers(c.admin_b)).status_code == 404
    assert (
        client.get(v1(f"/resources/{resource.id}"), headers=auth_headers(c.admin_b)).status_code
        == 404
    )
    assert (
        client.get(v1("/resources/review-queue"), headers=auth_headers(c.admin_b)).json()["data"]
        == []
    )

    queue_a = client.get(v1("/resources/review-queue"), headers=auth_headers(c.admin_a)).json()
    assert [r["id"] for r in queue_a["data"]] == [str(resource.id)]
    queue_platform = client.get(
        v1("/resources/review-queue"), headers=auth_headers(c.platform)
    ).json()
    assert str(resource.id) in [r["id"] for r in queue_platform["data"]]

    assert client.post(url("start-review"), headers=auth_headers(c.admin_a)).status_code == 200
    db.refresh(resource)
    assert resource.status == "UNDER_REVIEW"


def test_students_and_providers_cannot_use_moderation_endpoints(
    api_client: TestClient, campus: Campus
) -> None:
    c = campus
    assert (
        api_client.get(v1("/resources/review-queue"), headers=auth_headers(c.student)).status_code
        == 403
    )
    assert (
        api_client.get(v1("/resources/review-queue"), headers=auth_headers(c.provider)).status_code
        == 403
    )
    assert api_client.get(v1("/resources/mine"), headers=auth_headers(c.student)).status_code == 403


# --------------------------------------------------------------------------- archive, delete, stats, listings


def test_archive_and_delete_rules(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    c, client = campus, api_client
    rid = publish_via_api(client, c)
    assert act(client, c.student, rid, "archive").status_code == 403
    assert act(client, c.provider2, rid, "archive").status_code == 403
    assert act(client, c.provider, rid, "archive").json()["data"]["status"] == "ARCHIVED"
    assert client.get(v1(f"/resources/{rid}")).status_code == 404  # no longer public
    assert (
        act(client, c.admin_a, rid, "publish").json()["data"]["status"] == "PUBLISHED"
    )  # staff can restore it

    assert (
        client.delete(v1(f"/resources/{rid}"), headers=auth_headers(c.provider)).status_code == 409
    )  # not a draft

    draft = make_resource(db, provider=c.provider, institution=c.inst_a, storage=storage)
    key = db.scalar(
        select(StoredFile.storage_key)
        .join(ResourceVersion, ResourceVersion.file_id == StoredFile.id)
        .where(ResourceVersion.resource_id == draft.id)
    )
    assert (
        client.delete(v1(f"/resources/{draft.id}"), headers=auth_headers(c.provider2)).status_code
        == 404
    )
    assert (
        client.delete(v1(f"/resources/{draft.id}"), headers=auth_headers(c.provider)).status_code
        == 200
    )
    assert db.get(Resource, draft.id) is None
    with pytest.raises(Exception):  # noqa: B017, PT011 - blob must be gone too
        b"".join(storage.open(key))


def test_stats_are_visible_to_owner_and_staff_only(api_client: TestClient, campus: Campus) -> None:
    c, client = campus, api_client
    rid = publish_via_api(client, c)
    client.post(v1(f"/resources/{rid}/download"), headers=auth_headers(c.student))
    stats = client.get(v1(f"/resources/{rid}/stats"), headers=auth_headers(c.provider))
    assert stats.status_code == 200
    assert stats.json()["data"]["downloads_total"] == 1
    assert (
        client.get(v1(f"/resources/{rid}/stats"), headers=auth_headers(c.admin_a)).status_code
        == 200
    )
    assert (
        client.get(v1(f"/resources/{rid}/stats"), headers=auth_headers(c.student)).status_code
        == 404
    )
    assert (
        client.get(v1(f"/resources/{rid}/stats"), headers=auth_headers(c.admin_b)).status_code
        == 404
    )


def test_my_resources_lists_only_my_own(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    c = campus
    mine = make_resource(db, provider=c.provider, institution=c.inst_a, storage=storage)
    make_resource(db, provider=c.provider2, institution=c.inst_a, storage=storage)
    body = api_client.get(v1("/resources/mine"), headers=auth_headers(c.provider)).json()
    assert [r["id"] for r in body["data"]] == [str(mine.id)]
    assert body["meta"]["total"] == 1
