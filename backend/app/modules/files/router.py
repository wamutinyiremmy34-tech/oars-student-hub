import uuid
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.deps import DbSession
from app.core.errors import NotFoundError, UnauthorizedError
from app.core.security import decode_download_token
from app.modules.files.models import StoredFile
from app.modules.users.models import User, UserStatus
from app.providers.deps import StorageDep
from app.providers.storage.base import StorageError

router = APIRouter(prefix="/downloads", tags=["downloads"])


@router.get("/{token}", summary="Fetch a file with a short-lived download link")
def download_file(token: str, db: DbSession, storage: StorageDep) -> StreamingResponse:
    """The link was minted by POST /resources/{id}/download after full authorization. It is bound to one
    user and one file and expires quickly; it carries no wider access."""
    claims = decode_download_token(token)
    try:
        user_id, file_id = uuid.UUID(claims["sub"]), uuid.UUID(claims["fid"])
    except ValueError as exc:
        raise UnauthorizedError(
            "This download link is invalid or has expired.", code="invalid_download_link"
        ) from exc

    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE:  # suspended after the link was issued
        raise UnauthorizedError(
            "This download link is invalid or has expired.", code="invalid_download_link"
        )
    stored = db.get(StoredFile, file_id)
    if stored is None or stored.scan_status == "INFECTED":
        raise NotFoundError("File not found.")
    try:
        chunks = storage.open(stored.storage_key)
    except StorageError as exc:
        raise NotFoundError("File not found.") from exc

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(stored.original_filename)}",
        "Content-Length": str(stored.size_bytes),
        "Cache-Control": "private, no-store",
    }
    return StreamingResponse(chunks, media_type=stored.mime_type, headers=headers)
