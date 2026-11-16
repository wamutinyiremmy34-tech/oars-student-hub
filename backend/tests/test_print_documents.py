"""Print document upload: server-side page counting, validation, privacy."""

import uuid

import pytest
from fastapi.testclient import TestClient
from helpers import (
    PrintCampus,
    auth_headers,
    make_client,
    make_pdf,
    new_order,
    place_order,
    upload_doc,
    v1,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.files.models import StoredFile
from app.modules.printing.models import PrintDocument

pytestmark = pytest.mark.integration


@pytest.fixture
def campus(db: Session) -> PrintCampus:
    return PrintCampus(db)


def test_page_count_is_decided_by_the_server_from_the_file(
    api_client: TestClient, campus: PrintCampus, db: Session, storage
) -> None:  # type: ignore[no-untyped-def]
    response = upload_doc(api_client, campus.student, pages=7)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["page_count"] == 7 and data["filename"] == "notes.pdf"
    assert (
        "storage" not in response.text.lower() and "print/" not in response.text
    )  # the key is never exposed

    document = db.get(PrintDocument, uuid.UUID(data["id"]))
    stored = db.get(StoredFile, document.file_id)
    assert stored.visibility == "PRIVATE" and stored.owner_id == campus.student.id
    assert stored.storage_key.startswith(
        f"print/{campus.student.id}/"
    )  # generated, per-student prefix
    assert b"".join(storage.open(stored.storage_key)).startswith(b"%PDF")


def test_a_client_supplied_page_count_is_ignored(
    api_client: TestClient, campus: PrintCampus
) -> None:
    response = api_client.post(
        v1("/print/documents"),
        files={"file": ("a.pdf", make_pdf(2), "application/pdf")},
        data={"page_count": "1"},
        headers=auth_headers(campus.student),
    )
    assert response.json()["data"]["page_count"] == 2


def test_images_count_as_one_page(api_client: TestClient, campus: PrintCampus) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    response = upload_doc(
        api_client, campus.student, name="scan.png", content=png, mime="image/png"
    )
    assert response.status_code == 201 and response.json()["data"]["page_count"] == 1


@pytest.mark.parametrize(
    ("name", "content", "status", "code"),
    [
        (
            "notes.pdf",
            b"MZ" + b"\x00" * 200,
            415,
            "unsupported_file_type",
        ),  # an .exe wearing a .pdf name
        ("page.pdf", b"<html><script>1</script></html>", 415, "unsupported_file_type"),
        ("notes.docx", b"PK\x03\x04", 415, "unsupported_file_type"),
        ("empty.pdf", b"", 400, "empty_file"),
        ("broken.pdf", b"%PDF-1.4\nthis is not a real pdf at all", 415, "unreadable_pdf"),
    ],
)
def test_unprintable_or_dangerous_files_are_rejected_and_nothing_is_stored(
    api_client: TestClient,
    campus: PrintCampus,
    db: Session,
    name: str,
    content: bytes,
    status: int,
    code: str,
) -> None:
    response = upload_doc(api_client, campus.student, name=name, content=content)
    assert (response.status_code, response.json()["error"]["code"]) == (status, code)
    assert db.scalar(select(func.count()).select_from(StoredFile)) == 0
    assert db.scalar(select(func.count()).select_from(PrintDocument)) == 0


def test_word_files_are_not_printable_even_though_valid_elsewhere(
    api_client: TestClient, campus: PrintCampus
) -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<x/>")
        archive.writestr("word/document.xml", "<x/>")
    response = upload_doc(api_client, campus.student, name="essay.docx", content=buffer.getvalue())
    assert (
        response.status_code == 415
    )  # printing accepts PDF and images only: page counts must be trustworthy


def test_page_and_size_limits(
    db: Session, campus: PrintCampus, storage, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    client = make_client(
        db, storage, monkeypatch, MAX_PRINT_PAGES_PER_DOCUMENT=2, MAX_UPLOAD_BYTES=4096
    )
    too_many = upload_doc(client, campus.student, pages=3)
    assert (too_many.status_code, too_many.json()["error"]["code"]) == (400, "too_many_pages")
    big = upload_doc(client, campus.student, content=make_pdf(1) + b"0" * 6000)
    assert (big.status_code, big.json()["error"]["code"]) == (413, "file_too_large")


def test_uploads_need_the_customer_permission(api_client: TestClient, campus: PrintCampus) -> None:
    assert (
        api_client.post(
            v1("/print/documents"), files={"file": ("a.pdf", make_pdf(), "application/pdf")}
        ).status_code
        == 401
    )
    assert (
        upload_doc(api_client, campus.operator).status_code == 403
    )  # an operator is not a customer


def test_someone_elses_document_cannot_be_ordered(
    api_client: TestClient, campus: PrintCampus
) -> None:
    doc = upload_doc(api_client, campus.student).json()["data"]["id"]
    stolen = place_order(api_client, campus.student2, campus.shop, [doc])
    assert (
        stolen.status_code == 400 and stolen.json()["error"]["code"] == "invalid_document"
    )  # same as "missing"
    assert new_order(api_client, campus.student, campus.shop)["status"] == "SUBMITTED"
