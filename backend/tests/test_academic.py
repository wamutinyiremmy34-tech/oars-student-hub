"""Academic hierarchy: database-level institution isolation and the catalogue API."""

import pytest
from fastapi.testclient import TestClient
from helpers import auth_headers, make_academic, make_institution, make_user, v1
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.academic.models import Course, Department, Faculty, Program, ProgramCourse
from app.modules.audit.models import AuditLog

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- database-level isolation


def _fail(db: Session, *objects: object) -> None:
    with pytest.raises(IntegrityError):
        db.add_all(objects)
        db.flush()
    db.rollback()


def test_a_department_cannot_hang_off_another_universitys_faculty(db: Session) -> None:
    a, b = make_institution(db), make_institution(db)
    tree = make_academic(db, a)
    _fail(db, Department(institution_id=b.id, faculty_id=tree.faculty.id, name="Smuggled"))


def test_program_and_course_departments_must_belong_to_the_same_faculty(db: Session) -> None:
    inst = make_institution(db)
    tree = make_academic(db, inst)
    other_faculty = Faculty(institution_id=inst.id, name="Other faculty")
    db.add(other_faculty)
    db.commit()
    _fail(
        db,
        Program(
            institution_id=inst.id,
            faculty_id=other_faculty.id,
            department_id=tree.department.id,
            name="Mismatch",
        ),
    )
    _fail(
        db,
        Course(
            institution_id=inst.id,
            faculty_id=other_faculty.id,
            department_id=tree.department.id,
            code="BAD1",
            title="Mismatch",
        ),
    )


def test_programs_and_courses_may_sit_directly_under_a_faculty(db: Session) -> None:
    inst = make_institution(db)
    tree = make_academic(db, inst)
    db.add_all(
        [
            Program(
                institution_id=inst.id,
                faculty_id=tree.faculty.id,
                department_id=None,
                name="No-department program",
            ),
            Course(
                institution_id=inst.id,
                faculty_id=tree.faculty.id,
                department_id=None,
                code="NODEPT1",
                title="No department",
            ),
        ]
    )
    db.commit()  # universities differ: a missing department level is valid


def test_courses_cannot_be_linked_across_institutions(db: Session) -> None:
    a, b = make_institution(db), make_institution(db)
    tree_a, tree_b = make_academic(db, a), make_academic(db, b)
    _fail(
        db,
        ProgramCourse(
            program_id=tree_a.program.id, course_id=tree_b.course.id, institution_id=a.id
        ),
    )


def test_course_codes_are_unique_per_institution_and_uppercase(db: Session) -> None:
    a, b = make_institution(db), make_institution(db)
    tree_a = make_academic(db, a, code="CSC1100")
    make_academic(db, b, code="CSC1100")  # same code at another university is a different course
    _fail(
        db,
        Course(
            institution_id=a.id, faculty_id=tree_a.faculty.id, code="CSC1100", title="Duplicate"
        ),
    )
    _fail(
        db,
        Course(
            institution_id=a.id, faculty_id=tree_a.faculty.id, code="csc9999", title="Lower case"
        ),
    )


# --------------------------------------------------------------------------- catalogue API


def test_public_catalogue_reads_walk_the_hierarchy(api_client: TestClient, db: Session) -> None:
    inst = make_institution(db)
    tree = make_academic(db, inst, code="CSC1201")
    inst_id = str(inst.id)

    faculties = api_client.get(v1("/faculties"), params={"institution_id": inst_id}).json()["data"]
    assert [f["id"] for f in faculties] == [str(tree.faculty.id)]
    departments = api_client.get(
        v1("/departments"), params={"faculty_id": str(tree.faculty.id)}
    ).json()["data"]
    assert [d["id"] for d in departments] == [str(tree.department.id)]
    programs = api_client.get(
        v1("/programs"),
        params={"institution_id": inst_id, "department_id": str(tree.department.id)},
    ).json()["data"]
    assert [p["id"] for p in programs] == [str(tree.program.id)]

    courses = api_client.get(
        v1("/courses"), params={"institution_id": inst_id, "program_id": str(tree.program.id)}
    ).json()
    assert [c["code"] for c in courses["data"]] == ["CSC1201"]
    assert courses["meta"] == {"page": 1, "page_size": 50, "total": 1}
    assert (
        api_client.get(v1("/courses"), params={"institution_id": inst_id, "q": "csc12"}).json()[
            "meta"
        ]["total"]
        == 1
    )
    assert (
        api_client.get(v1("/courses"), params={"institution_id": inst_id, "q": "zzz"}).json()[
            "meta"
        ]["total"]
        == 0
    )
    assert api_client.get(v1("/courses")).status_code == 422  # institution_id is required


def test_catalogue_is_scoped_to_the_requested_institution_and_hides_inactive(
    api_client: TestClient, db: Session
) -> None:
    a, b = make_institution(db), make_institution(db)
    tree_a = make_academic(db, a)
    make_academic(db, b)
    only_a = api_client.get(v1("/faculties"), params={"institution_id": str(a.id)}).json()["data"]
    assert [f["institution_id"] for f in only_a] == [str(a.id)]

    tree_a.faculty.is_active = False
    db.commit()
    assert (
        api_client.get(v1("/faculties"), params={"institution_id": str(a.id)}).json()["data"] == []
    )


# --------------------------------------------------------------------------- administration


@pytest.fixture
def world(db: Session):  # type: ignore[no-untyped-def]
    a, b = make_institution(db), make_institution(db)
    return {
        "a": a, "b": b,
        "tree_a": make_academic(db, a), "tree_b": make_academic(db, b),
        "admin_a": make_user(db, roles=[("ADMIN", a.id)]),
        "platform": make_user(db, roles=[("ADMIN", None)]),
        "student": make_user(db, institution=a, roles=[("STUDENT", a.id)]),
    }  # fmt: skip


def post(client: TestClient, path: str, user, body):  # type: ignore[no-untyped-def]
    return client.post(v1(path), json=body, headers=auth_headers(user))


def test_scoped_admin_manages_only_their_own_institution(
    api_client: TestClient, db: Session, world
) -> None:  # type: ignore[no-untyped-def]
    w = world
    own = post(
        api_client,
        "/faculties",
        w["admin_a"],
        {
            "institution_id": str(w["a"].id),
            "name": "School of Law",
            "kind": "SCHOOL",
            "code": "LAW",
        },
    )
    assert own.status_code == 201 and own.json()["data"]["kind"] == "SCHOOL"
    assert (
        db.scalar(select(AuditLog).where(AuditLog.action == "catalog.faculty_created")) is not None
    )

    assert (
        post(
            api_client,
            "/faculties",
            w["admin_a"],
            {"institution_id": str(w["b"].id), "name": "Intruder"},
        ).status_code
        == 403
    )
    assert (
        post(
            api_client,
            "/faculties",
            w["student"],
            {"institution_id": str(w["a"].id), "name": "Student faculty"},
        ).status_code
        == 403
    )
    assert (
        post(
            api_client,
            "/faculties",
            w["platform"],
            {"institution_id": str(w["b"].id), "name": "By platform"},
        ).status_code
        == 201
    )

    foreign = api_client.patch(
        v1(f"/faculties/{w['tree_b'].faculty.id}"),
        json={"name": "Renamed"},
        headers=auth_headers(w["admin_a"]),
    )
    assert foreign.status_code == 404  # looks nonexistent, not forbidden
    ours = api_client.patch(
        v1(f"/faculties/{w['tree_a'].faculty.id}"),
        json={"name": "Renamed"},
        headers=auth_headers(w["admin_a"]),
    )
    assert ours.status_code == 200 and ours.json()["data"]["name"] == "Renamed"


def test_children_cannot_be_created_under_another_institutions_parent(
    api_client: TestClient, world
) -> None:  # type: ignore[no-untyped-def]
    w = world
    foreign_faculty = str(w["tree_b"].faculty.id)
    assert (
        post(
            api_client,
            "/departments",
            w["admin_a"],
            {"faculty_id": foreign_faculty, "name": "Dept"},
        ).status_code
        == 404
    )
    assert (
        post(
            api_client, "/programs", w["admin_a"], {"faculty_id": foreign_faculty, "name": "Prog"}
        ).status_code
        == 404
    )
    assert (
        post(
            api_client,
            "/courses",
            w["admin_a"],
            {"faculty_id": foreign_faculty, "code": "X100", "title": "Course"},
        ).status_code
        == 404
    )


def test_department_must_belong_to_the_chosen_faculty(
    api_client: TestClient, db: Session, world
) -> None:  # type: ignore[no-untyped-def]
    w = world
    other = post(
        api_client,
        "/faculties",
        w["admin_a"],
        {"institution_id": str(w["a"].id), "name": "Second faculty"},
    ).json()["data"]
    mismatched = post(
        api_client,
        "/courses",
        w["admin_a"],
        {
            "faculty_id": other["id"],
            "department_id": str(w["tree_a"].department.id),
            "code": "ZZ100",
            "title": "Mismatch",
        },
    )
    assert (
        mismatched.status_code == 400 and mismatched.json()["error"]["code"] == "invalid_department"
    )


def test_course_codes_are_normalised_and_duplicates_conflict(api_client: TestClient, world) -> None:  # type: ignore[no-untyped-def]
    w = world
    body = {
        "faculty_id": str(w["tree_a"].faculty.id),
        "department_id": str(w["tree_a"].department.id),
        "code": " csc2100 ",
        "title": "Algorithms",
        "credit_units": 4,
    }
    created = post(api_client, "/courses", w["admin_a"], body)
    assert created.status_code == 201 and created.json()["data"]["code"] == "CSC2100"
    duplicate = post(api_client, "/courses", w["admin_a"], body)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "already_exists"
    # ...and the failed insert did not poison the session for later requests
    assert (
        api_client.get(v1("/courses"), params={"institution_id": str(w["a"].id)}).status_code == 200
    )


def test_linking_courses_to_programs(api_client: TestClient, world) -> None:  # type: ignore[no-untyped-def]
    w = world
    new_course = post(
        api_client,
        "/courses",
        w["admin_a"],
        {"faculty_id": str(w["tree_a"].faculty.id), "code": "ABC100", "title": "Intro"},
    ).json()["data"]
    link = post(
        api_client,
        f"/programs/{w['tree_a'].program.id}/courses",
        w["admin_a"],
        {"course_id": new_course["id"], "year_of_study": 2, "semester": 1},
    )
    assert link.status_code == 201
    foreign = post(
        api_client,
        f"/programs/{w['tree_a'].program.id}/courses",
        w["platform"],
        {"course_id": str(w["tree_b"].course.id)},
    )
    assert foreign.status_code == 400 and foreign.json()["error"]["code"] == "invalid_course"
    assert (
        post(
            api_client,
            f"/programs/{w['tree_b'].program.id}/courses",
            w["admin_a"],
            {"course_id": new_course["id"]},
        ).status_code
        == 404
    )


def test_institution_management_is_platform_level(api_client: TestClient, world) -> None:  # type: ignore[no-untyped-def]
    w = world
    assert (
        post(
            api_client, "/institutions", w["admin_a"], {"name": "New University", "code": "nu"}
        ).status_code
        == 403
    )  # scoped admins cannot add universities
    created = post(
        api_client, "/institutions", w["platform"], {"name": "Gulu University", "code": "gu"}
    )
    assert created.status_code == 201 and created.json()["data"]["code"] == "GU"
    assert (
        post(
            api_client, "/institutions", w["platform"], {"name": "Gulu University", "code": "gu2"}
        ).status_code
        == 409
    )

    rename = api_client.patch(
        v1(f"/institutions/{w['a'].id}"),
        json={"name": "Renamed University"},
        headers=auth_headers(w["admin_a"]),
    )
    assert rename.status_code == 200
    elsewhere = api_client.patch(
        v1(f"/institutions/{w['b'].id}"),
        json={"name": "Hijacked"},
        headers=auth_headers(w["admin_a"]),
    )
    assert elsewhere.status_code == 404
    deactivate = api_client.patch(
        v1(f"/institutions/{w['a'].id}"),
        json={"is_active": False},
        headers=auth_headers(w["admin_a"]),
    )
    assert deactivate.status_code == 403  # (de)activation is platform-level
    assert (
        api_client.patch(
            v1(f"/institutions/{w['a'].id}"),
            json={"is_active": False},
            headers=auth_headers(w["platform"]),
        ).status_code
        == 200
    )
