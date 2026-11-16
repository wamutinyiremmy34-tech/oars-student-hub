"""Database integrity for resources, versions, entitlements, bookmarks and moderation history."""

import uuid
from datetime import UTC, datetime

import pytest
from helpers import Campus, category, make_resource, put_file
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.academic.models import Course
from app.modules.files.models import StoredFile
from app.modules.resources.models import (
    Bookmark,
    CourseResource,
    Entitlement,
    Resource,
    ResourceReview,
    ResourceVersion,
    Tag,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> Campus:
    return Campus(db)


def _fail(db: Session, *objects: object, error: type[Exception] = IntegrityError) -> None:
    with pytest.raises(error):
        db.add_all(objects)
        db.flush()
    db.rollback()


def _resource(c: Campus, **overrides: object) -> Resource:
    fields: dict[str, object] = {
        "institution_id": c.inst_a.id, "provider_id": c.provider.id,
        "category_id": category(c.db).id, "title": "T", "access_type": "FREE",
    }  # fmt: skip
    return Resource(**{**fields, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "fields",
    [
        {"access_type": "PREMIUM", "price_ugx": None},
        {"access_type": "PREMIUM", "price_ugx": 0},
        {"access_type": "PREMIUM", "price_ugx": -5},
        {"access_type": "FREE", "price_ugx": 100},
        {"access_type": "GOLD"},
        {"status": "LIVE"},
        {"academic_year": 1800},
    ],
)
def test_resource_check_constraints(db: Session, campus: Campus, fields: dict[str, object]) -> None:
    _fail(db, _resource(campus, **fields))


def test_valid_free_and_premium_resources_are_accepted(db: Session, campus: Campus) -> None:
    db.add_all([_resource(campus), _resource(campus, access_type="PREMIUM", price_ugx=5000)])
    db.commit()


def test_search_vector_is_maintained_by_the_database(db: Session, campus: Campus) -> None:
    resource = _resource(campus, title="Quantum mechanics", description="wave functions")
    db.add(resource)
    db.commit()
    match = "SELECT count(*) FROM resources WHERE id = :id AND search_vector @@ websearch_to_tsquery('english', :q)"
    assert db.execute(text(match), {"id": resource.id, "q": "wave"}).scalar_one() == 1
    resource.title = "Thermodynamics"
    resource.description = "entropy"
    db.commit()
    assert db.execute(text(match), {"id": resource.id, "q": "wave"}).scalar_one() == 0
    assert db.execute(text(match), {"id": resource.id, "q": "entropy"}).scalar_one() == 1


def test_only_one_version_per_resource_can_be_current(db: Session, campus: Campus, storage) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="PUBLISHED"
    )
    second = ResourceVersion(
        resource_id=resource.id, version_number=2, file_id=put_file(db, storage, campus.provider).id,
        is_current=True, created_by_user_id=campus.provider.id,
    )  # fmt: skip
    _fail(db, second)  # version 1 is already current
    other = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage, status="PUBLISHED"
    )
    assert other.id != resource.id  # a different resource may have its own current version


def test_version_numbers_are_unique_per_resource(db: Session, campus: Campus, storage) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage
    )
    dup = ResourceVersion(
        resource_id=resource.id, version_number=1, file_id=put_file(db, storage, campus.provider).id,
        created_by_user_id=campus.provider.id,
    )  # fmt: skip
    _fail(db, dup)


def test_a_resource_cannot_be_linked_to_another_institutions_course(
    db: Session, campus: Campus, storage
) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db, provider=campus.provider, institution=campus.inst_a, storage=storage
    )
    foreign_course = campus.tree_b.course
    _fail(
        db,
        CourseResource(
            resource_id=resource.id, course_id=foreign_course.id, institution_id=campus.inst_a.id
        ),
    )
    _fail(
        db,
        CourseResource(
            resource_id=resource.id, course_id=foreign_course.id, institution_id=campus.inst_b.id
        ),
    )
    own = db.get(Course, campus.tree_a.course.id)
    db.add(
        CourseResource(resource_id=resource.id, course_id=own.id, institution_id=campus.inst_a.id)
    )
    db.commit()


def test_entitlements_and_bookmarks_are_unique_per_user_and_resource(
    db: Session, campus: Campus, storage
) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db,
        provider=campus.provider,
        institution=campus.inst_a,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
    )
    db.add_all(
        [
            Entitlement(user_id=campus.student.id, resource_id=resource.id, source="ADMIN_GRANT"),
            Bookmark(user_id=campus.student.id, resource_id=resource.id),
        ]
    )
    db.commit()
    _fail(db, Entitlement(user_id=campus.student.id, resource_id=resource.id, source="PROMO"))
    _fail(db, Bookmark(user_id=campus.student.id, resource_id=resource.id))
    _fail(
        db, Entitlement(user_id=campus.student2.id, resource_id=resource.id, source="FREEBIE")
    )  # unknown source


def test_resources_with_entitlements_cannot_be_deleted(
    db: Session, campus: Campus, storage
) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db,
        provider=campus.provider,
        institution=campus.inst_a,
        storage=storage,
        status="PUBLISHED",
        access="PREMIUM",
    )
    db.add(Entitlement(user_id=campus.student.id, resource_id=resource.id, source="PURCHASE"))
    db.commit()
    with pytest.raises(
        IntegrityError
    ):  # ON DELETE RESTRICT: paid-for access is never silently destroyed
        db.execute(text("DELETE FROM resources WHERE id = :id"), {"id": resource.id})
    db.rollback()


def test_rejections_must_carry_a_reason(db: Session, campus: Campus, storage) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db,
        provider=campus.provider,
        institution=campus.inst_a,
        storage=storage,
        status="UNDER_REVIEW",
    )
    base = {
        "resource_id": resource.id,
        "actor_user_id": campus.admin_a.id,
        "from_status": "UNDER_REVIEW",
        "to_status": "REJECTED",
    }
    _fail(db, ResourceReview(decision="REJECTED", reason=None, **base))
    _fail(db, ResourceReview(decision="REJECTED", reason="   ", **base))
    _fail(db, ResourceReview(decision="MAYBE", reason="x", **base))
    db.add(ResourceReview(decision="REJECTED", reason="Unreadable scan", **base))
    db.commit()


def test_deleting_a_draft_cascades_to_its_dependents(db: Session, campus: Campus, storage) -> None:  # type: ignore[no-untyped-def]
    resource = make_resource(
        db,
        provider=campus.provider,
        institution=campus.inst_a,
        storage=storage,
        course=campus.tree_a.course,
        tags=("cascade-me",),
    )
    db.execute(text("DELETE FROM resources WHERE id = :id"), {"id": resource.id})
    for table in ("resource_versions", "course_resources", "resource_tags"):
        assert (
            db.execute(
                text(f"SELECT count(*) FROM {table} WHERE resource_id = :id"), {"id": resource.id}
            ).scalar_one()
            == 0
        )


def test_tags_are_lowercase_and_files_are_non_empty(db: Session, campus: Campus) -> None:
    _fail(db, Tag(name="MixedCase"))
    _fail(
        db,
        StoredFile(
            storage_key=f"k/{uuid.uuid4().hex}",
            original_filename="a.pdf",
            mime_type="application/pdf",
            size_bytes=0,
            sha256="0" * 64,
            owner_id=campus.provider.id,
        ),
    )
    _fail(
        db,
        StoredFile(
            storage_key=f"k/{uuid.uuid4().hex}",
            original_filename="a.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            sha256="0" * 64,
            owner_id=campus.provider.id,
            visibility="SECRET",
        ),
    )


def test_categories_are_seeded_and_extensible(db: Session) -> None:
    from app.modules.resources.models import ResourceCategory

    slugs = set(db.scalars(select(ResourceCategory.slug)))
    assert {
        "notes",
        "past-papers",
        "handouts",
        "study-guides",
        "reference-material",
        "academic-documents",
    } <= slugs
    db.add(
        ResourceCategory(name="Lab manuals", slug="lab-manuals")
    )  # a new type needs no code change
    db.commit()
    assert datetime.now(UTC)  # (keeps the import used)
