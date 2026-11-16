"""Security primitives: Argon2id passwords, JWT access tokens, opaque (refresh) tokens.

Phase 1 provides the primitives only. Registration, login, refresh rotation and RBAC arrive in Phase 4.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.core.errors import UnauthorizedError

ACCESS_TOKEN_TYPE = "access"
_hasher = PasswordHasher()  # argon2-cffi defaults to Argon2id with RFC 9106 low-memory parameters


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(subject: str, *, ttl: timedelta | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    lifetime = ttl if ttl is not None else timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "type": ACCESS_TOKEN_TYPE,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],  # pinned: rejects alg=none and algorithm confusion
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired token.", code="invalid_token") from exc
    if claims.get("type") != ACCESS_TOKEN_TYPE:
        raise UnauthorizedError("Invalid or expired token.", code="invalid_token")
    return claims


def generate_opaque_token(nbytes: int = 48) -> str:
    """Random URL-safe token for refresh tokens, email verification and password reset."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Store this, never the raw token. Tokens have 384 bits of entropy, so SHA-256 is sufficient."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


DOWNLOAD_TOKEN_TYPE = "download"


def create_download_token(*, user_id: str, file_id: str, ttl_seconds: int) -> str:
    """Short-lived capability to fetch ONE stored file. Issued only after authorization succeeded."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "fid": file_id,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": uuid.uuid4().hex,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "type": DOWNLOAD_TOKEN_TYPE,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_download_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud", "fid"]},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError(
            "This download link is invalid or has expired.", code="invalid_download_link"
        ) from exc
    if (
        claims.get("type") != DOWNLOAD_TOKEN_TYPE
    ):  # an access token must never work as a download link
        raise UnauthorizedError(
            "This download link is invalid or has expired.", code="invalid_download_link"
        )
    return claims
