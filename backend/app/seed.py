"""Development/E2E demo data. Refuses to run in production. Idempotent: existing demo rows are reused.

All demo accounts share one well-known password, so this must never touch a real deployment.
"""

import hashlib
import io
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.academic.models import Course, Department, Faculty, Program, ProgramCourse
from app.modules.files.models import StoredFile
from app.modules.institutions.models import Institution
from app.modules.printing.models import PrintPricingRule, PrintShop, PrintShopStaff
from app.modules.rbac.service import add_user_role, get_role
from app.modules.resources.models import (
    AccessType,
    CourseResource,
    Resource,
    ResourceCategory,
    ResourceStatus,
    ResourceVersion,
)
from app.modules.users.models import StudentProfile, User
from app.providers.storage.base import StorageBackend

DEMO_PASSWORD = "Demo-password-123"
DEMO_EMAILS = {
    "student": "student@demo.oars.dev",
    "provider": "provider@demo.oars.dev",
    "admin": "admin@demo.oars.dev",  # ADMIN scoped to Makerere
    "operator": "operator@demo.oars.dev",  # works at the demo print shop
}
TINY_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def _user(db: Session, email: str, name: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email, full_name=name, password_hash=hash_password(DEMO_PASSWORD),
            status="ACTIVE", email_verified_at=datetime.now(UTC),
        )  # fmt: skip
        db.add(user)
        db.flush()
    return user


def _grant(db: Session, user: User, role: str, institution_id: uuid.UUID) -> None:
    try:
        add_user_role(
            db,
            user_id=user.id,
            role=get_role(db, role),
            institution_id=institution_id,
            granted_by=None,
        )
    except Exception:  # noqa: BLE001 - already assigned on a re-run
        db.rollback()


def seed_demo(db: Session, storage: StorageBackend) -> dict[str, str]:
    mak = db.scalar(select(Institution).where(Institution.code == "MAK"))
    if mak is None:
        raise RuntimeError("Run `alembic upgrade head` first: the Makerere institution is missing.")

    student = _user(db, DEMO_EMAILS["student"], "Demo Student")
    provider = _user(db, DEMO_EMAILS["provider"], "Demo Provider")
    admin = _user(db, DEMO_EMAILS["admin"], "Demo Admin")
    operator = _user(db, DEMO_EMAILS["operator"], "Demo Operator")
    db.commit()
    if student.student_profile is None:
        db.add(StudentProfile(user_id=student.id, institution_id=mak.id))
    for user, role in (
        (student, "STUDENT"),
        (provider, "RESOURCE_PROVIDER"),
        (admin, "ADMIN"),
        (operator, "PRINTING_OPERATOR"),
    ):
        _grant(db, user, role, mak.id)
    db.commit()

    faculty = db.scalar(
        select(Faculty).where(
            Faculty.institution_id == mak.id,
            Faculty.name == "College of Computing and Information Sciences",
        )
    )
    if faculty is None:
        faculty = Faculty(
            institution_id=mak.id,
            name="College of Computing and Information Sciences",
            kind="COLLEGE",
            code="COCIS",
        )
        db.add(faculty)
        db.flush()
        department = Department(
            institution_id=mak.id, faculty_id=faculty.id, name="Computer Science"
        )
        db.add(department)
        db.flush()
        program = Program(
            institution_id=mak.id,
            faculty_id=faculty.id,
            department_id=department.id,
            name="BSc Computer Science",
            level="BACHELORS",
            duration_years=3,
        )
        db.add(program)
        db.flush()
        courses = [
            Course(
                institution_id=mak.id,
                faculty_id=faculty.id,
                department_id=department.id,
                code="CSC1100",
                title="Introduction to Programming",
                credit_units=4,
            ),
            Course(
                institution_id=mak.id,
                faculty_id=faculty.id,
                department_id=department.id,
                code="CSC1201",
                title="Data Structures",
                credit_units=4,
            ),
        ]
        db.add_all(courses)
        db.flush()
        db.add_all(
            ProgramCourse(
                program_id=program.id,
                course_id=c.id,
                institution_id=mak.id,
                year_of_study=1,
                semester=1,
            )
            for c in courses
        )
        db.commit()

    notes = db.scalar(select(ResourceCategory).where(ResourceCategory.slug == "notes"))
    papers = db.scalar(select(ResourceCategory).where(ResourceCategory.slug == "past-papers"))
    assert notes and papers
    by_code = {c.code: c for c in db.scalars(select(Course).where(Course.institution_id == mak.id))}

    specs = [
        (
            "Introduction to Programming - Lecture Notes",
            notes,
            AccessType.FREE,
            None,
            "CSC1100",
            "Variables, loops and functions explained with worked examples.",
        ),
        (
            "Data Structures - Past Paper 2024",
            papers,
            AccessType.PREMIUM,
            5000,
            "CSC1201",
            "Full 2024 examination paper with marking guide.",
        ),
    ]
    for title, category, access, price, code, description in specs:
        if db.scalar(
            select(Resource.id).where(Resource.title == title, Resource.institution_id == mak.id)
        ):
            continue
        resource = Resource(
            institution_id=mak.id, provider_id=provider.id, category_id=category.id, title=title,
            description=description, preview_text="Preview: " + description, access_type=access,
            price_ugx=price, status=ResourceStatus.PUBLISHED, academic_year=2024, published_at=datetime.now(UTC),
        )  # fmt: skip
        db.add(resource)
        db.flush()
        key = f"resources/{resource.id}/{uuid.uuid4().hex}.pdf"
        storage.put(key, io.BytesIO(TINY_PDF), content_type="application/pdf")
        stored = StoredFile(
            storage_key=key, original_filename=title.split(" - ")[0].replace(" ", "-") + ".pdf",
            mime_type="application/pdf", size_bytes=len(TINY_PDF), sha256=hashlib.sha256(TINY_PDF).hexdigest(),
            owner_id=provider.id, visibility="PRIVATE", scan_status="NOT_SCANNED",
        )  # fmt: skip
        db.add(stored)
        db.flush()
        db.add(
            ResourceVersion(
                resource_id=resource.id,
                version_number=1,
                file_id=stored.id,
                is_current=True,
                created_by_user_id=provider.id,
            )
        )
        db.add(
            CourseResource(
                resource_id=resource.id, course_id=by_code[code].id, institution_id=mak.id
            )
        )
        db.commit()
    _seed_print_shop(db, mak, operator)
    return {**DEMO_EMAILS, "password": DEMO_PASSWORD}


def _seed_print_shop(db: Session, institution: Institution, operator: User) -> None:
    shop = db.scalar(
        select(PrintShop).where(
            PrintShop.institution_id == institution.id, PrintShop.name == "Main Library Print Shop"
        )
    )
    if shop is None:
        shop = PrintShop(
            institution_id=institution.id,
            name="Main Library Print Shop",
            location="Ground floor, Main Library",
        )
        db.add(shop)
        db.flush()
        rules = [
            ("PER_PAGE", "A4", "BW", None, None, 50),
            ("PER_PAGE", "A4", "BW", True, None, 40),
            ("PER_PAGE", "A4", "COLOR", None, None, 300),
            ("PER_PAGE", "A3", "BW", None, None, 150),
            ("PER_COPY", None, None, None, "staple", 100),
            ("PER_ORDER", None, None, None, "binding", 2000),
        ]
        db.add_all(
            PrintPricingRule(shop_id=shop.id, kind=k, paper_size=ps, color_mode=cm, duplex=dx, option_key=ok_, amount_ugx=amt)
            for k, ps, cm, dx, ok_, amt in rules
        )  # fmt: skip
    if db.get(PrintShopStaff, (shop.id, operator.id)) is None:
        db.add(PrintShopStaff(shop_id=shop.id, user_id=operator.id))
    db.commit()
