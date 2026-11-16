from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)


def test_password_hash_roundtrip_uses_argon2id() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$argon2id$")
    assert "correct horse" not in hashed
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False
    assert password_needs_rehash(hashed) is False


def test_password_hashes_are_salted() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password_returns_false_for_garbage_hash() -> None:
    assert verify_password("anything", "not-a-hash") is False


def test_access_token_roundtrip() -> None:
    claims = decode_access_token(create_access_token("user-123"))
    assert claims["sub"] == "user-123"
    assert claims["type"] == "access"
    assert {"exp", "iat", "jti", "iss"} <= claims.keys()


def test_expired_token_is_rejected() -> None:
    token = create_access_token("user-123", ttl=timedelta(seconds=-5))
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_access_token("user-123")
    header, payload, signature = token.split(".")
    # Change the FIRST signature character: all 6 bits of it are significant, so the signature
    # is guaranteed to differ (changing trailing characters can leave the decoded bytes intact).
    flipped = ("B" if signature[0] != "B" else "C") + signature[1:]
    with pytest.raises(UnauthorizedError):
        decode_access_token(".".join([header, payload, flipped]))


def test_token_signed_with_other_key_is_rejected() -> None:
    forged = jwt.encode({"sub": "x"}, "another-key-" * 4, algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        decode_access_token(forged)


def test_alg_none_token_is_rejected() -> None:
    settings = get_settings()
    unsigned = jwt.encode(
        {"sub": "x", "iss": settings.jwt_issuer, "type": "access"}, None, algorithm="none"
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(unsigned)


def test_wrong_token_type_is_rejected() -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "x",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": "abc",
            "iss": settings.jwt_issuer,
            "type": "refresh",
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)


def test_opaque_tokens_are_unique_and_hash_is_stable() -> None:
    a, b = generate_opaque_token(), generate_opaque_token()
    assert a != b
    assert len(a) >= 48
    assert hash_token(a) == hash_token(a)
    assert hash_token(a) != hash_token(b)
    assert len(hash_token(a)) == 64
    assert a not in hash_token(a)
