"""Test helpers: factories and small utilities (plain functions so tests stay readable)."""

import re
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.modules.institutions.models import Institution
from app.modules.rbac.service import add_user_role, get_role
from app.modules.users.models import StudentProfile, User
from app.providers.email import EmailMessage

PASSWORD = "correct-horse-battery"
REFRESH_COOKIE = "oars_refresh"


class MemoryEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)

    def last_token(self) -> str:
        match = re.search(r"token=([A-Za-z0-9_-]+)", self.sent[-1].body)
        assert match, "no token link in the last email"
        return match.group(1)


def override_db(app: FastAPI, db: Session) -> None:
    def _get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _get_db


def make_institution(db: Session, *, active: bool = True) -> Institution:
    suffix = uuid.uuid4().hex[:8]
    institution = Institution(
        name=f"Test University {suffix}",
        slug=f"test-{suffix}",
        code=suffix.upper(),
        is_active=active,
    )
    db.add(institution)
    db.commit()
    return institution


def make_user(
    db: Session,
    *,
    email: str | None = None,
    password: str = PASSWORD,
    institution: Institution | None = None,
    roles: Sequence[tuple[str, uuid.UUID | None]] = (),
    status: str = "ACTIVE",
) -> User:
    """Create a user directly in the database (no HTTP). `roles` is [(role_name, institution_id|None)]."""
    user = User(
        email=(email or f"user-{uuid.uuid4().hex[:10]}@example.com").lower(),
        full_name="Test User",
        password_hash=hash_password(password),
        status=status,
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    if institution is not None:
        db.add(StudentProfile(user_id=user.id, institution_id=institution.id))
    for role_name, institution_id in roles:
        add_user_role(
            db,
            user_id=user.id,
            role=get_role(db, role_name),
            institution_id=institution_id,
            granted_by=None,
        )
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# --------------------------------------------------------------------------- academic + resources

import hashlib  # noqa: E402
import io  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.modules.academic.models import Course, Department, Faculty, Program, ProgramCourse  # noqa: E402
from app.modules.files.models import StoredFile  # noqa: E402
from app.modules.resources.models import (  # noqa: E402
    CourseResource,
    Resource,
    ResourceCategory,
    ResourceTag,
    ResourceVersion,
    Tag,
)

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def make_academic(
    db: Session, institution: Institution, *, code: str | None = None
) -> SimpleNamespace:
    """Faculty > Department > Program > Course (linked) for one institution."""
    suffix = uuid.uuid4().hex[:6].upper()
    faculty = Faculty(institution_id=institution.id, name=f"Faculty {suffix}", kind="FACULTY")
    db.add(faculty)
    db.flush()
    department = Department(
        institution_id=institution.id, faculty_id=faculty.id, name=f"Dept {suffix}"
    )
    db.add(department)
    db.flush()
    program = Program(
        institution_id=institution.id, faculty_id=faculty.id, department_id=department.id,
        name=f"Program {suffix}", level="BACHELORS",
    )  # fmt: skip
    course = Course(
        institution_id=institution.id, faculty_id=faculty.id, department_id=department.id,
        code=code or f"C{suffix}", title=f"Course {suffix}",
    )  # fmt: skip
    db.add_all([program, course])
    db.flush()
    db.add(ProgramCourse(program_id=program.id, course_id=course.id, institution_id=institution.id))
    db.commit()
    return SimpleNamespace(faculty=faculty, department=department, program=program, course=course)


def category(db: Session, slug: str = "notes") -> ResourceCategory:
    found = db.scalar(select(ResourceCategory).where(ResourceCategory.slug == slug))
    assert found is not None, f"category {slug} should be seeded by the migration"
    return found


def put_file(
    db: Session, storage, owner: User, content: bytes = PDF, *, scan: str = "NOT_SCANNED"
) -> StoredFile:  # type: ignore[no-untyped-def]
    key = f"resources/test/{uuid.uuid4().hex}.pdf"
    storage.put(key, io.BytesIO(content), content_type="application/pdf")
    stored = StoredFile(
        storage_key=key, original_filename="notes.pdf", mime_type="application/pdf", size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(), owner_id=owner.id, visibility="PRIVATE", scan_status=scan,
    )  # fmt: skip
    db.add(stored)
    db.flush()
    return stored


def make_resource(
    db: Session,
    *,
    provider: User,
    institution: Institution,
    storage=None,  # type: ignore[no-untyped-def]
    status: str = "DRAFT",
    access: str = "FREE",
    price: int | None = None,
    title: str | None = None,
    description: str = "Some study material",
    course: Course | None = None,
    tags: tuple[str, ...] = (),
    cat: str = "notes",
    year: int | None = None,
    with_file: bool = True,
) -> Resource:
    from datetime import UTC, datetime

    if access == "PREMIUM" and price is None:
        price = 5000
    resource = Resource(
        institution_id=institution.id, provider_id=provider.id, category_id=category(db, cat).id,
        title=title or f"Resource {uuid.uuid4().hex[:6]}", description=description, access_type=access,
        price_ugx=price if access == "PREMIUM" else None, status=status, academic_year=year,
        published_at=datetime.now(UTC) if status == "PUBLISHED" else None,
    )  # fmt: skip
    db.add(resource)
    db.flush()
    if with_file:
        assert storage is not None
        stored = put_file(db, storage, provider)
        db.add(
            ResourceVersion(
                resource_id=resource.id, version_number=1, file_id=stored.id,
                is_current=status == "PUBLISHED", created_by_user_id=provider.id,
            )
        )  # fmt: skip
    if course is not None:
        db.add(
            CourseResource(
                resource_id=resource.id, course_id=course.id, institution_id=institution.id
            )
        )
    for name in tags:
        tag = db.scalar(select(Tag).where(Tag.name == name)) or Tag(name=name)
        db.add(tag)
        db.flush()
        db.add(ResourceTag(resource_id=resource.id, tag_id=tag.id))
    db.commit()
    return resource


def v1(path: str) -> str:
    return f"/api/v1{path}"


class Campus:
    """Two universities with academic trees and one user of every kind. Shared by the resource tests."""

    def __init__(self, db: Session) -> None:
        self.inst_a = make_institution(db)
        self.inst_b = make_institution(db)
        self.tree_a = make_academic(db, self.inst_a, code="MTH1101")
        self.tree_b = make_academic(db, self.inst_b, code="MTH1101")
        a, b = self.inst_a.id, self.inst_b.id
        self.provider = make_user(db, roles=[("RESOURCE_PROVIDER", a)])
        self.provider2 = make_user(db, roles=[("RESOURCE_PROVIDER", a)])
        self.provider_b = make_user(db, roles=[("RESOURCE_PROVIDER", b)])
        self.student = make_user(db, institution=self.inst_a, roles=[("STUDENT", a)])
        self.student2 = make_user(db, institution=self.inst_a, roles=[("STUDENT", a)])
        self.admin_a = make_user(db, roles=[("ADMIN", a)])
        self.admin_b = make_user(db, roles=[("ADMIN", b)])
        self.platform = make_user(db, roles=[("ADMIN", None)])
        self.db = db

    def create_payload(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "institution_id": str(self.inst_a.id),
            "category_id": str(category(self.db).id),
            "title": "Calculus lecture notes",
            "description": "Limits, derivatives and integrals.",
            "access_type": "FREE",
            "tags": ["Calculus", "math", "calculus"],
            "course_ids": [str(self.tree_a.course.id)],
        }
        return {**base, **overrides}


# --------------------------------------------------------------------------- printing and payments

from app.modules.printing.models import PrintPricingRule, PrintShop, PrintShopStaff  # noqa: E402


def make_pdf(pages: int = 1) -> bytes:
    """A small but structurally valid PDF with `pages` blank pages (a correct xref table)."""
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>",
    ]
    objects += ["<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>"] * pages
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out


DEFAULT_RULES = [
    ("PER_PAGE", "A4", "BW", None, None, 50),
    ("PER_PAGE", "A4", "BW", True, None, 40),
    ("PER_PAGE", "A4", "COLOR", None, None, 300),
    ("PER_COPY", None, None, None, "staple", 100),
    ("PER_ORDER", None, None, None, "binding", 2000),
]


def make_shop(
    db: Session, institution: Institution, *, name: str | None = None, rules=DEFAULT_RULES, **fields
) -> PrintShop:  # type: ignore[no-untyped-def]
    shop = PrintShop(
        institution_id=institution.id, name=name or f"Shop {uuid.uuid4().hex[:6]}", **fields
    )
    db.add(shop)
    db.flush()
    db.add_all(
        PrintPricingRule(shop_id=shop.id, kind=k, paper_size=ps, color_mode=cm, duplex=dx, option_key=ok, amount_ugx=amt)
        for k, ps, cm, dx, ok, amt in rules
    )  # fmt: skip
    db.commit()
    return shop


def staff(db: Session, shop: PrintShop, user: User) -> None:
    db.add(PrintShopStaff(shop_id=shop.id, user_id=user.id))
    db.commit()


class PrintCampus:
    """Two institutions; two shops in the first; one operator per shop; students, an admin, a platform admin."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.inst = make_institution(db)
        self.inst_b = make_institution(db)
        self.shop = make_shop(db, self.inst)
        self.shop2 = make_shop(db, self.inst)  # several shops per institution
        self.shop_b = make_shop(db, self.inst_b)
        a, b = self.inst.id, self.inst_b.id
        self.student = make_user(db, institution=self.inst, roles=[("STUDENT", a)])
        self.student2 = make_user(db, institution=self.inst, roles=[("STUDENT", a)])
        self.operator = make_user(db, roles=[("PRINTING_OPERATOR", a)])
        self.operator2 = make_user(db, roles=[("PRINTING_OPERATOR", a)])
        self.operator_b = make_user(db, roles=[("PRINTING_OPERATOR", b)])
        self.stray_operator = make_user(
            db, roles=[("PRINTING_OPERATOR", a)]
        )  # role but works at no shop
        self.admin = make_user(db, roles=[("ADMIN", a)])
        self.admin_b = make_user(db, roles=[("ADMIN", b)])
        self.platform = make_user(db, roles=[("ADMIN", None)])
        staff(db, self.shop, self.operator)
        staff(db, self.shop2, self.operator2)
        staff(db, self.shop_b, self.operator_b)


def upload_doc(
    client,
    user,
    pages: int = 3,
    name: str = "notes.pdf",
    content: bytes | None = None,
    mime: str = "application/pdf",
):  # type: ignore[no-untyped-def]
    return client.post(
        v1("/print/documents"),
        files={"file": (name, content if content is not None else make_pdf(pages), mime)},
        headers=auth_headers(user),
    )


def order_body(shop, doc_ids, method: str = "PAY_ON_PICKUP", **item):  # type: ignore[no-untyped-def]
    base = {
        "copies": 1,
        "paper_size": "A4",
        "color_mode": "BW",
        "duplex": False,
        "options": {},
        **item,
    }
    return {
        "shop_id": str(shop.id),
        "items": [{"document_id": d, **base} for d in doc_ids],
        "payment_method": method,
    }


def place_order(
    client,
    user,
    shop,
    doc_ids,
    method: str = "PAY_ON_PICKUP",
    *,
    key: str | None = None,
    extra=None,
    **item,
):  # type: ignore[no-untyped-def]
    headers = {**auth_headers(user), **({"Idempotency-Key": key} if key else {})}
    return client.post(
        v1("/print/orders"),
        json={**order_body(shop, doc_ids, method, **item), **(extra or {})},
        headers=headers,
    )


def new_order(client, user, shop, *, pages: int = 3, method: str = "PAY_ON_PICKUP", **item) -> dict:  # type: ignore[no-untyped-def,type-arg]
    doc = upload_doc(client, user, pages)
    assert doc.status_code == 201, doc.text
    response = place_order(client, user, shop, [doc.json()["data"]["id"]], method, **item)
    assert response.status_code == 201, response.text
    return response.json()["data"]  # type: ignore[no-any-return]


def op(client, user, order_id, action: str, body=None):  # type: ignore[no-untyped-def]
    return client.post(
        v1(f"/operator/orders/{order_id}/{action}"), json=body, headers=auth_headers(user)
    )


def run_to_ready(client, operator, order_id) -> None:  # type: ignore[no-untyped-def]
    for action in ("accept", "printing", "ready"):
        response = op(client, operator, order_id, action)
        assert response.status_code == 200, (action, response.text)


def pickup_code_for(order_id) -> str:  # type: ignore[no-untyped-def]
    from app.core.config import get_settings
    from app.modules.printing.service import pickup_code, pickup_secret

    return pickup_code(uuid.UUID(str(order_id)), pickup_secret(get_settings()))


def make_client(db: Session, storage, monkeypatch, **env):  # type: ignore[no-untyped-def]
    """A client for an app built AFTER the given settings overrides (e.g. MAX_PICKUP_ORDER_TOTAL_UGX=1000)."""
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import create_app

    for key, value in env.items():
        monkeypatch.setenv(key.upper(), str(value))
    get_settings.cache_clear()
    app = create_app()
    override_db(app, db)
    app.state.storage = storage
    return TestClient(app)


def fake_provider(client):  # type: ignore[no-untyped-def]
    return client.app.state.payment_providers["fake"]
