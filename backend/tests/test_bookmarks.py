import pytest
from fastapi.testclient import TestClient
from helpers import Campus, auth_headers, make_resource, v1
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.resources.models import Bookmark

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> Campus:
    return Campus(db)


def test_add_list_and_remove_own_bookmarks(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    r = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="PUBLISHED"
    )
    me = auth_headers(campus.student)

    assert api_client.put(v1(f"/bookmarks/{r.id}"), headers=me).status_code == 200
    assert api_client.put(v1(f"/bookmarks/{r.id}"), headers=me).status_code == 200  # idempotent
    assert db.scalar(select(func.count()).select_from(Bookmark)) == 1

    listing = api_client.get(v1("/bookmarks"), headers=me).json()
    assert [x["id"] for x in listing["data"]] == [str(r.id)]
    assert listing["data"][0]["is_bookmarked"] is True and listing["meta"]["total"] == 1

    assert api_client.delete(v1(f"/bookmarks/{r.id}"), headers=me).status_code == 200
    assert api_client.delete(v1(f"/bookmarks/{r.id}"), headers=me).status_code == 200  # idempotent
    assert api_client.get(v1("/bookmarks"), headers=me).json()["data"] == []


def test_users_can_only_touch_their_own_bookmarks(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    r = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="PUBLISHED"
    )
    api_client.put(v1(f"/bookmarks/{r.id}"), headers=auth_headers(campus.student))

    assert (
        api_client.get(v1("/bookmarks"), headers=auth_headers(campus.student2)).json()["data"] == []
    )
    api_client.delete(
        v1(f"/bookmarks/{r.id}"), headers=auth_headers(campus.student2)
    )  # removes only student2's (none)
    assert (
        db.scalar(
            select(func.count()).select_from(Bookmark).where(Bookmark.user_id == campus.student.id)
        )
        == 1
    )


def test_only_published_resources_can_be_bookmarked_and_archived_ones_disappear(
    api_client: TestClient, campus: Campus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    draft = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="DRAFT"
    )
    live = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="PUBLISHED"
    )
    me = auth_headers(campus.student)

    assert api_client.put(v1(f"/bookmarks/{draft.id}"), headers=me).status_code == 404
    assert (
        api_client.put(
            v1("/bookmarks/00000000-0000-0000-0000-000000000042"), headers=me
        ).status_code
        == 404
    )
    api_client.put(v1(f"/bookmarks/{live.id}"), headers=me)
    live.status = "ARCHIVED"
    db.commit()
    assert api_client.get(v1("/bookmarks"), headers=me).json()["data"] == []


def test_bookmarks_require_authentication(api_client: TestClient, campus: Campus) -> None:
    assert api_client.get(v1("/bookmarks")).status_code == 401
    assert api_client.put(v1("/bookmarks/00000000-0000-0000-0000-000000000042")).status_code == 401
