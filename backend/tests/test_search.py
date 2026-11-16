"""PostgreSQL search: relevance, filters, sorting, pagination, and injection safety."""

import pytest
from fastapi.testclient import TestClient
from helpers import (
    Campus,
    auth_headers,
    make_institution,
    make_resource,
    make_user,
    v1,
)
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> Campus:
    return Campus(db)


def search(client: TestClient, **params: object) -> dict:  # type: ignore[type-arg]
    response = client.get(v1("/search"), params={k: v for k, v in params.items() if v is not None})
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def titles(body: dict) -> list[str]:  # type: ignore[type-arg]
    return [r["title"] for r in body["data"]]


@pytest.fixture
def library(db: Session, campus: Campus, storage):  # type: ignore[no-untyped-def]
    c = campus
    kw = {"provider": c.provider, "institution": c.inst_a, "storage": storage}
    return {
        "title_hit": make_resource(
            db,
            title="Calculus Lecture Notes",
            description="Limits and integrals",
            status="PUBLISHED",
            course=c.tree_a.course,
            tags=("calculus", "math"),
            year=2023,
            **kw,
        ),
        "desc_hit": make_resource(
            db,
            title="Study guide",
            description="Revision exercises on calculus derivatives",
            status="PUBLISHED",
            cat="study-guides",
            access="PREMIUM",
            year=2024,
            **kw,
        ),
        "other": make_resource(
            db,
            title="Physics handout",
            description="Kinematics",
            status="PUBLISHED",
            cat="handouts",
            **kw,
        ),
        "draft": make_resource(db, title="Calculus draft", status="DRAFT", **kw),
        "submitted": make_resource(db, title="Calculus submitted", status="SUBMITTED", **kw),
        "archived": make_resource(db, title="Calculus archived", status="ARCHIVED", **kw),
        "in_b": make_resource(
            db,
            title="Calculus at B",
            status="PUBLISHED",
            provider=c.provider_b,
            institution=c.inst_b,
            storage=storage,
        ),
    }


def test_only_published_resources_are_ever_returned(
    api_client: TestClient, campus: Campus, library
) -> None:  # type: ignore[no-untyped-def]
    body = search(api_client, q="calculus")
    assert set(titles(body)) == {"Calculus Lecture Notes", "Study guide", "Calculus at B"}
    everything = search(api_client, page_size=50)
    assert not {"Calculus draft", "Calculus submitted", "Calculus archived"} & set(
        titles(everything)
    )


def test_full_text_search_matches_titles_descriptions_and_word_forms(
    api_client: TestClient, campus: Campus, library
) -> None:  # type: ignore[no-untyped-def]
    a = str(campus.inst_a.id)
    assert "Study guide" in titles(
        search(api_client, q="derivative", institution_id=a)
    )  # 'derivatives' stems
    assert "Calculus Lecture Notes" in titles(search(api_client, q="integral", institution_id=a))
    assert titles(search(api_client, q="kinematics", institution_id=a)) == ["Physics handout"]
    assert search(api_client, q="zebra", institution_id=a)["data"] == []


def test_title_matches_rank_above_description_only_matches(
    api_client: TestClient, campus: Campus, library
) -> None:  # type: ignore[no-untyped-def]
    ordered = titles(search(api_client, q="calculus", institution_id=str(campus.inst_a.id)))
    assert ordered.index("Calculus Lecture Notes") < ordered.index("Study guide")


@pytest.mark.parametrize("q", ["MTH1101", "mth1101", "MTH 1101", "mth 11"])
def test_course_codes_are_searchable_in_any_spelling(
    api_client: TestClient, campus: Campus, library, q: str
) -> None:  # type: ignore[no-untyped-def]
    found = titles(search(api_client, q=q, institution_id=str(campus.inst_a.id)))
    assert found == ["Calculus Lecture Notes"]


def test_tags_are_searchable_and_filterable(
    api_client: TestClient, campus: Campus, library
) -> None:  # type: ignore[no-untyped-def]
    a = str(campus.inst_a.id)
    assert titles(search(api_client, q="math", institution_id=a)) == ["Calculus Lecture Notes"]
    assert titles(search(api_client, tag="MATH", institution_id=a)) == ["Calculus Lecture Notes"]
    assert search(api_client, tag="nonexistent", institution_id=a)["data"] == []


def test_filters_by_institution_category_access_year_and_academic_structure(
    api_client: TestClient, campus: Campus, library
) -> None:  # type: ignore[no-untyped-def]
    c, a = campus, str(campus.inst_a.id)
    assert set(titles(search(api_client, institution_id=str(c.inst_b.id)))) == {"Calculus at B"}
    assert titles(search(api_client, institution_id=a, category="handouts")) == ["Physics handout"]
    assert titles(search(api_client, institution_id=a, access="PREMIUM")) == ["Study guide"]
    assert titles(search(api_client, institution_id=a, academic_year=2023)) == [
        "Calculus Lecture Notes"
    ]
    tree = c.tree_a
    for key, value in (
        ("course_id", tree.course.id),
        ("faculty_id", tree.faculty.id),
        ("department_id", tree.department.id),
        ("program_id", tree.program.id),
    ):
        assert titles(search(api_client, **{key: str(value)})) == ["Calculus Lecture Notes"], key
    # the same course code at the OTHER university is a different course and finds nothing here
    assert search(api_client, course_id=str(c.tree_b.course.id))["data"] == []


def test_sorting(api_client: TestClient, campus: Campus, library) -> None:  # type: ignore[no-untyped-def]
    a = str(campus.inst_a.id)
    by_title = titles(search(api_client, institution_id=a, sort="title"))
    assert by_title == sorted(by_title, key=str.lower)
    assert (
        titles(search(api_client, institution_id=a, sort="newest"))[0] == "Physics handout"
    )  # published last


def test_pagination_is_stable_and_reports_totals(
    api_client: TestClient, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    inst = make_institution(db)
    provider = make_user(db, roles=[("RESOURCE_PROVIDER", inst.id)])
    for i in range(5):
        make_resource(
            db,
            provider=provider,
            institution=inst,
            storage=storage,
            status="PUBLISHED",
            title=f"Item {i}",
        )
    pages = [
        search(api_client, institution_id=str(inst.id), page=n, page_size=2) for n in (1, 2, 3)
    ]
    assert [len(p["data"]) for p in pages] == [2, 2, 1]
    assert all(
        p["meta"] == {"page": n, "page_size": 2, "total": 5}
        for n, p in zip((1, 2, 3), pages, strict=True)
    )
    ids = [r["id"] for p in pages for r in p["data"]]
    assert len(ids) == len(set(ids)) == 5
    assert search(api_client, institution_id=str(inst.id), page=4, page_size=2)["data"] == []


@pytest.mark.parametrize(
    "q",
    [
        "%",
        "_",
        "' OR 1=1 --",
        '"unbalanced',
        "a' ; DROP TABLE resources; --",
        "\\",
        "(((",
        "ñ ✓ 😀",
    ],
)
def test_hostile_queries_are_safe(api_client: TestClient, campus: Campus, library, q: str) -> None:  # type: ignore[no-untyped-def]
    body = search(api_client, q=q, institution_id=str(campus.inst_a.id))
    assert body["data"] == []  # LIKE wildcards are escaped, so '%' does not match everything
    assert search(api_client, q="calculus", institution_id=str(campus.inst_a.id))[
        "data"
    ]  # the table is still there


@pytest.mark.parametrize(
    "params",
    [
        {"page_size": 51},
        {"page": 0},
        {"unknown": "x"},
        {"sort": "random"},
        {"access": "GOLD"},
        {"q": "x" * 101},
        {"institution_id": "nope"},
    ],
)
def test_invalid_query_parameters_are_rejected(
    api_client: TestClient, params: dict[str, object]
) -> None:
    assert api_client.get(v1("/search"), params=params).status_code == 422


def test_browse_endpoint_and_viewer_specific_bookmark_flag(
    api_client: TestClient, campus: Campus, library
) -> None:  # type: ignore[no-untyped-def]
    rid = str(library["title_hit"].id)
    api_client.put(v1(f"/bookmarks/{rid}"), headers=auth_headers(campus.student))
    mine = api_client.get(
        v1("/resources"),
        params={"institution_id": str(campus.inst_a.id)},
        headers=auth_headers(campus.student),
    ).json()
    other = api_client.get(
        v1("/resources"),
        params={"institution_id": str(campus.inst_a.id)},
        headers=auth_headers(campus.student2),
    ).json()
    flag = lambda body: {r["id"]: r["is_bookmarked"] for r in body["data"]}[rid]  # noqa: E731
    assert flag(mine) is True and flag(other) is False
    assert all("storage" not in str(r).lower() for r in mine["data"])
