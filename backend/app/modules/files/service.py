import hashlib
import tempfile
import uuid
from collections.abc import Callable
from typing import BinaryIO

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, PayloadTooLargeError, UnsupportedMediaTypeError
from app.modules.files.models import StoredFile
from app.modules.files.validation import FileKind, secure_display_name, sniff
from app.providers.scanner import MalwareScanner
from app.providers.storage.base import StorageBackend

_CHUNK = 64 * 1024


def store_upload(
    db: Session,
    *,
    upload: UploadFile,
    owner_id: uuid.UUID,
    key_prefix: str,
    storage: StorageBackend,
    scanner: MalwareScanner,
    max_bytes: int,
    allowed_exts: frozenset[str] | None = None,
    inspect: Callable[[BinaryIO, FileKind], None] | None = None,
) -> StoredFile:
    """Validate and store an upload. Order matters: size cap while reading, then magic bytes,
    then malware scan, and only then is anything written to storage."""
    digest = hashlib.sha256()
    size = 0
    with tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024) as buffer:
        while chunk := upload.file.read(_CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise PayloadTooLargeError(
                    f"Files can be at most {max_bytes // (1024 * 1024)} MB.", code="file_too_large"
                )
            digest.update(chunk)
            buffer.write(chunk)
        if size == 0:
            raise BadRequestError("The file is empty.", code="empty_file")

        kind = sniff(buffer)
        if kind is None:
            raise UnsupportedMediaTypeError(
                "Only PDF, Word, PowerPoint, Excel, PNG, JPEG and plain-text files are allowed.",
                code="unsupported_file_type",
            )
        if allowed_exts is not None and kind.ext not in allowed_exts:
            raise UnsupportedMediaTypeError(
                f"This kind of file is not accepted here ({', '.join(sorted(allowed_exts)).upper()} only).",
                code="unsupported_file_type",
            )
        if (
            inspect is not None
        ):  # e.g. count pages; may raise, in which case nothing has been stored
            buffer.seek(0)
            inspect(buffer, kind)
        buffer.seek(0)
        scan_status = scanner.scan(buffer)
        if scan_status == "INFECTED":
            raise BadRequestError(
                "This file was rejected by the security scan.", code="file_rejected"
            )

        key = f"{key_prefix}/{uuid.uuid4().hex}.{kind.ext}"  # generated: never derived from user input
        buffer.seek(0)
        storage.put(key, buffer, content_type=kind.mime)

    stored = StoredFile(
        storage_key=key,
        original_filename=secure_display_name(upload.filename, kind),
        mime_type=kind.mime,
        size_bytes=size,
        sha256=digest.hexdigest(),
        owner_id=owner_id,
        visibility="PRIVATE",
        scan_status=scan_status,
    )
    db.add(stored)
    db.flush()
    return stored
