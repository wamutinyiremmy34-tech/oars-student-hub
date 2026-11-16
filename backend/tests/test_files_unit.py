"""Upload validation, storage and download-token unit tests (no database)."""

import io
import zipfile
from datetime import timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_download_token,
    decode_access_token,
    decode_download_token,
)
from app.modules.files.validation import (
    DOCX,
    JPEG,
    PDF,
    PNG,
    PPTX,
    TEXT,
    XLSX,
    secure_display_name,
    sniff,
)
from app.providers.storage.base import StorageError
from app.providers.storage.local import LocalStorage


def zip_with(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "<x/>")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"%PDF-1.7\nrest", PDF),
        (b"\x89PNG\r\n\x1a\n" + b"0" * 20, PNG),
        (b"\xff\xd8\xff\xe0" + b"0" * 20, JPEG),
        (zip_with("[Content_Types].xml", "word/document.xml"), DOCX),
        (zip_with("[Content_Types].xml", "ppt/presentation.xml"), PPTX),
        (zip_with("[Content_Types].xml", "xl/workbook.xml"), XLSX),
        ("Plain notes with unicode: Nakasero ✓".encode(), TEXT),
    ],
)
def test_allowed_types_are_detected_from_content(content: bytes, expected: object) -> None:
    assert sniff(io.BytesIO(content)) == expected


@pytest.mark.parametrize(
    "content",
    [
        b"MZ\x90\x00" + b"\x00" * 50,  # Windows executable
        b"\x7fELF\x02\x01\x01" + b"\x00" * 50,  # Linux executable
        b"#!/bin/sh\nrm -rf /\n",  # script
        b"<html><script>alert(1)</script></html>",  # HTML
        b'<?xml version="1.0"?><svg onload="alert(1)"/>',  # SVG / XML
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 50,  # legacy Office (macro-capable)
        b"\x00\x01\x02\x03binary",  # unknown binary
        zip_with("a.txt", "b.txt"),  # generic zip
        zip_with("[Content_Types].xml", "word/document.xml", "word/vbaProject.bin"),  # macros
        zip_with("[Content_Types].xml"),  # OOXML shell without a document part
        b"PK\x03\x04not really a zip",
    ],
)
def test_everything_else_is_rejected(content: bytes) -> None:
    assert sniff(io.BytesIO(content)) is None


def test_content_not_extension_decides() -> None:
    exe_named_pdf = b"MZ" + b"\x00" * 100
    assert sniff(io.BytesIO(exe_named_pdf)) is None  # the filename is never even consulted


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\amina\\notes final.docx", "notes final.pdf"),
        ("résumé<script>.exe", "rsumscript.pdf"),
        ("", "document.pdf"),
        (None, "document.pdf"),
        ("...", "document.pdf"),
        ("a" * 300 + ".pdf", "a" * 80 + ".pdf"),
    ],
)
def test_display_names_are_sanitised_and_use_the_detected_extension(
    original: str | None, expected: str
) -> None:
    assert secure_display_name(original, PDF) == expected


# --------------------------------------------------------------------------- local storage


def test_local_storage_roundtrip_and_delete(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalStorage(tmp_path)
    storage.put(
        "resources/a/file.pdf", io.BytesIO(b"hello" * 100_000), content_type="application/pdf"
    )
    assert b"".join(storage.open("resources/a/file.pdf")) == b"hello" * 100_000
    storage.delete("resources/a/file.pdf")
    with pytest.raises(StorageError):
        storage.open("resources/a/file.pdf")
    storage.delete("resources/a/file.pdf")  # deleting twice is fine


@pytest.mark.parametrize("key", ["../outside.pdf", "/etc/passwd", "a/../../b", "a\\b", ""])
def test_local_storage_rejects_traversal_keys(tmp_path, key: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(StorageError):
        LocalStorage(tmp_path).put(key, io.BytesIO(b"x"), content_type="text/plain")


def test_local_storage_leaves_no_temp_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    LocalStorage(tmp_path).put("k/file.txt", io.BytesIO(b"x"), content_type="text/plain")
    assert [p.name for p in (tmp_path / "k").iterdir()] == ["file.txt"]


def test_local_storage_cannot_sign_urls(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert (
        LocalStorage(tmp_path).presigned_get_url("k", filename="f", content_type="x", expires_in=60)
        is None
    )


# --------------------------------------------------------------------------- download tokens


def test_download_token_roundtrip_is_short_lived() -> None:
    token = create_download_token(user_id="u1", file_id="f1", ttl_seconds=60)
    claims = decode_download_token(token)
    assert (claims["sub"], claims["fid"]) == ("u1", "f1")
    assert claims["exp"] - claims["iat"] == 60


def test_access_and_download_tokens_are_not_interchangeable() -> None:
    access = create_access_token("u1")
    download = create_download_token(user_id="u1", file_id="f1", ttl_seconds=60)
    with pytest.raises(UnauthorizedError):
        decode_download_token(access)
    with pytest.raises(UnauthorizedError):
        decode_access_token(download)


def test_expired_or_forged_download_tokens_are_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        decode_download_token(create_download_token(user_id="u", file_id="f", ttl_seconds=-5))
    forged = jwt.encode({"sub": "u", "fid": "f", "type": "download"}, "x" * 40, algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        decode_download_token(forged)
    settings = get_settings()
    assert timedelta(seconds=settings.download_url_ttl_seconds) <= timedelta(minutes=15)
