"""End-to-end authentication tests against real PostgreSQL (transaction-per-test)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from helpers import (
    PASSWORD,
    REFRESH_COOKIE,
    MemoryEmailSender,
    auth_headers,
    make_institution,
    make_user,
    override_db,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_token
from app.modules.audit.models import AuditLog
from app.modules.auth.models import PasswordResetToken, RefreshToken, VerificationToken
from app.modules.institutions.models import Institution
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User

pytestmark = pytest.mark.integration

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
EMAIL = "amina@example.com"


def register(client: TestClient, institution: Institution, **overrides: object):  # type: ignore[no-untyped-def]
    payload = {
        "email": EMAIL,
        "password": PASSWORD,
        "full_name": "Amina Nakato",
        "institution_id": str(institution.id),
        **overrides,
    }
    return client.post(REGISTER, json=payload)


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post(LOGIN, json={"email": email, "password": password})


def refresh_with(client: TestClient, token: str):  # type: ignore[no-untyped-def]
    """Send a specific refresh cookie, bypassing the client's cookie jar."""
    client.cookies.clear()
    return client.post(REFRESH, headers={"Cookie": f"{REFRESH_COOKIE}={token}"})


def audit_actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)))


# --------------------------------------------------------------------------- registration


def test_register_creates_user_profile_role_token_and_email(
    api_client: TestClient, db: Session, email_outbox: MemoryEmailSender
) -> None:
    institution = make_institution(db)
    response = register(api_client, institution, student_number="2024/U/001")

    assert response.status_code == 201
    user_json = response.json()["data"]["user"]
    assert user_json["email"] == EMAIL
    assert user_json["email_verified"] is False
    assert "password" not in response.text.lower()
    assert "hash" not in response.text.lower()

    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    assert user.student_profile is not None
    assert user.student_profile.institution_id == institution.id
    assert user.student_profile.student_number == "2024/U/001"

    roles = db.execute(
        select(Role.name, UserRole.institution_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    ).all()
    assert roles == [("STUDENT", institution.id)]  # scoped, never platform-wide

    assert db.scalar(select(func.count()).select_from(VerificationToken)) == 1
    assert len(email_outbox.sent) == 1
    assert "verify-email?token=" in email_outbox.sent[0].body
    assert "auth.registered" in audit_actions(db)


def test_duplicate_registration_is_rejected_case_insensitively(
    api_client: TestClient, db: Session
) -> None:
    institution = make_institution(db)
    assert register(api_client, institution).status_code == 201
    duplicate = register(api_client, institution, email=EMAIL.upper())
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_taken"
    assert db.scalar(select(func.count()).select_from(User).where(User.email == EMAIL)) == 1


def test_duplicate_student_number_in_same_institution_is_rejected(
    api_client: TestClient, db: Session
) -> None:
    institution = make_institution(db)
    assert register(api_client, institution, student_number="S1").status_code == 201
    second = register(api_client, institution, email="b@example.com", student_number="S1")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "student_number_taken"


def test_registration_validation_never_echoes_the_password(
    api_client: TestClient, db: Session
) -> None:
    institution = make_institution(db)
    response = register(api_client, institution, password="tooshort")
    assert response.status_code == 422
    assert "tooshort" not in response.text


def test_registration_rejects_unknown_or_inactive_institution(
    api_client: TestClient, db: Session
) -> None:
    unknown = api_client.post(
        REGISTER,
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "full_name": "A",
            "institution_id": str(uuid.uuid4()),
        },
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "invalid_institution"

    inactive = make_institution(db, active=False)
    assert register(api_client, inactive).json()["error"]["code"] == "invalid_institution"


def test_institution_list_is_public_and_hides_inactive(api_client: TestClient, db: Session) -> None:
    active = make_institution(db)
    inactive = make_institution(db, active=False)
    response = api_client.get("/api/v1/institutions")
    assert response.status_code == 200
    ids = {i["id"] for i in response.json()["data"]}
    assert str(active.id) in ids
    assert str(inactive.id) not in ids
    names = {i["name"] for i in response.json()["data"]}
    assert "Makerere University" in names  # seeded by the migration


# --------------------------------------------------------------------------- login


def test_login_returns_access_token_and_httponly_refresh_cookie(
    api_client: TestClient, db: Session
) -> None:
    register(api_client, make_institution(db))
    response = login(api_client)

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"access_token", "token_type", "expires_in"}  # no refresh token in the body
    assert data["expires_in"] == get_settings().access_token_ttl_minutes * 60

    cookie_header = response.headers["set-cookie"].lower()
    assert f"{REFRESH_COOKIE}=" in cookie_header
    assert "httponly" in cookie_header
    assert "path=/api/v1/auth" in cookie_header
    assert "samesite=lax" in cookie_header
    assert data["access_token"] not in cookie_header

    stored = db.scalar(select(RefreshToken))
    assert stored is not None
    raw = response.cookies.get(REFRESH_COOKIE)
    assert raw is not None
    assert stored.token_hash == hash_token(raw) != raw  # only the hash is stored


def test_me_returns_profile_roles_and_permissions_without_secrets(
    api_client: TestClient, db: Session
) -> None:
    institution = make_institution(db)
    register(api_client, institution)
    token = login(api_client).json()["data"]["access_token"]

    response = api_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["email"] == EMAIL
    assert data["student_profile"]["institution_id"] == str(institution.id)
    assert data["roles"] == [{"role": "STUDENT", "institution_id": str(institution.id)}]
    granted = {(g["permission"], g["institution_id"]) for g in data["permissions"]}
    assert ("order:create", str(institution.id)) in granted
    assert not any(code == "user:suspend" for code, _ in granted)
    for forbidden in ("password", "hash", "refresh", "secret"):
        assert forbidden not in response.text.lower()


def test_invalid_logins_are_indistinguishable(api_client: TestClient, db: Session) -> None:
    make_user(db, email=EMAIL)
    wrong_password = login(api_client, password="wrong-password-123")
    unknown_email = login(api_client, email="nobody@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    a, b = wrong_password.json()["error"], unknown_email.json()["error"]
    assert a["code"] == b["code"] == "invalid_credentials"
    assert a["message"] == b["message"]
    assert "set-cookie" not in wrong_password.headers
    assert "auth.login_failed" in audit_actions(
        db
    )  # failures are recorded despite the error response


def test_suspended_user_cannot_log_in(api_client: TestClient, db: Session) -> None:
    make_user(db, email=EMAIL, status="SUSPENDED")
    response = login(api_client)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_suspended"
    # A wrong password on a suspended account must NOT reveal the suspension.
    assert login(api_client, password="wrong-password-123").status_code == 401


# --------------------------------------------------------------------------- access tokens


def test_me_requires_a_valid_access_token(api_client: TestClient, db: Session) -> None:
    user = make_user(db)
    assert api_client.get("/api/v1/me").status_code == 401
    assert (
        api_client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    )
    assert api_client.get("/api/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401
    assert api_client.get("/api/v1/me", headers=auth_headers(user)).status_code == 200


def test_expired_access_token_is_rejected(api_client: TestClient, db: Session) -> None:
    user = make_user(db)
    expired = create_access_token(str(user.id), ttl=timedelta(seconds=-5))
    response = api_client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_token_for_a_nonexistent_user_is_rejected(api_client: TestClient) -> None:
    token = create_access_token(str(uuid.uuid4()))
    assert (
        api_client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


# --------------------------------------------------------------------------- refresh / logout


def test_refresh_rotates_the_token_and_keeps_the_family(
    api_client: TestClient, db: Session
) -> None:
    make_user(db, email=EMAIL)
    first = login(api_client)
    old_cookie = first.cookies.get(REFRESH_COOKIE)

    second = api_client.post(REFRESH)  # cookie jar sends the refresh cookie automatically
    assert second.status_code == 200
    new_cookie = second.cookies.get(REFRESH_COOKIE)
    assert new_cookie and new_cookie != old_cookie
    assert second.json()["data"]["access_token"]

    rows = list(db.scalars(select(RefreshToken).order_by(RefreshToken.created_at)))
    assert len(rows) == 2
    assert rows[0].family_id == rows[1].family_id
    assert rows[0].revoked_reason == "rotated"
    assert rows[1].revoked_at is None


def test_replaying_a_rotated_refresh_token_revokes_the_whole_family(
    api_client: TestClient, db: Session
) -> None:
    make_user(db, email=EMAIL)
    stolen = login(api_client).cookies.get(REFRESH_COOKIE)
    current = api_client.post(REFRESH).cookies.get(REFRESH_COOKIE)
    assert stolen and current

    replay = refresh_with(api_client, stolen)  # attacker (or buggy client) replays the old token
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "invalid_refresh_token"

    # The legitimate, newest token is now dead too: the session was assumed compromised.
    assert refresh_with(api_client, current).status_code == 401
    assert all(r.revoked_at is not None for r in db.scalars(select(RefreshToken)))
    assert "auth.refresh_reuse_detected" in audit_actions(db)


def test_refresh_with_missing_unknown_or_expired_token_fails(
    api_client: TestClient, db: Session
) -> None:
    user = make_user(db, email=EMAIL)
    assert api_client.post(REFRESH).status_code == 401
    assert refresh_with(api_client, "not-a-real-token").status_code == 401

    api_client.cookies.clear()
    login(api_client)
    row = db.scalar(select(RefreshToken).where(RefreshToken.user_id == user.id))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert api_client.post(REFRESH).status_code == 401


def test_logout_revokes_the_session_and_clears_the_cookie(
    api_client: TestClient, db: Session
) -> None:
    make_user(db, email=EMAIL)
    cookie = login(api_client).cookies.get(REFRESH_COOKIE)
    assert cookie

    response = api_client.post(LOGOUT)
    assert response.status_code == 200
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert refresh_with(api_client, cookie).status_code == 401
    stored = db.scalar(select(RefreshToken))
    assert stored is not None and stored.revoked_reason == "logout"
    assert "auth.logout" in audit_actions(db)


def test_logout_is_idempotent_without_a_session(api_client: TestClient) -> None:
    assert api_client.post(LOGOUT).status_code == 200


def test_refresh_and_logout_reject_foreign_origins(api_client: TestClient, db: Session) -> None:
    make_user(db, email=EMAIL)
    login(api_client)
    evil = {"Origin": "https://evil.example"}
    for path in (REFRESH, LOGOUT):
        response = api_client.post(path, headers=evil)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "origin_not_allowed"
    assert api_client.post(REFRESH, headers={"Origin": "http://localhost:5173"}).status_code == 200


# --------------------------------------------------------------------------- suspension


def test_suspension_takes_effect_immediately_and_revokes_sessions(
    api_client: TestClient, db: Session
) -> None:
    institution = make_institution(db)
    admin = make_user(db, roles=[("ADMIN", institution.id)])
    student = make_user(
        db, email=EMAIL, institution=institution, roles=[("STUDENT", institution.id)]
    )

    access = login(api_client).json()["data"]["access_token"]
    refresh_cookie = api_client.cookies.get(REFRESH_COOKIE)
    assert refresh_cookie
    assert (
        api_client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"}).status_code
        == 200
    )

    suspend = api_client.post(
        f"/api/v1/users/{student.id}/suspend", json={"reason": "abuse"}, headers=auth_headers(admin)
    )
    assert suspend.status_code == 200

    # The already-issued access token dies at once (the user is re-read on every request)...
    assert (
        api_client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"}).status_code
        == 401
    )
    # ...the refresh token can no longer mint new ones...
    assert refresh_with(api_client, refresh_cookie).status_code == 401
    # ...and signing in again is refused.
    assert login(api_client).json()["error"]["code"] == "account_suspended"


# --------------------------------------------------------------------------- email verification


def test_email_verification_flow(
    api_client: TestClient, db: Session, email_outbox: MemoryEmailSender
) -> None:
    register(api_client, make_institution(db))
    token = email_outbox.last_token()

    assert api_client.post("/api/v1/auth/verify", json={"token": token}).status_code == 200
    me = api_client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {login(api_client).json()['data']['access_token']}"},
    )
    assert me.json()["data"]["user"]["email_verified"] is True

    reused = api_client.post("/api/v1/auth/verify", json={"token": token})
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "invalid_token"
    bogus = api_client.post("/api/v1/auth/verify", json={"token": "x" * 40})
    assert bogus.status_code == 400


# --------------------------------------------------------------------------- password reset


def test_forgot_password_gives_the_same_answer_for_known_and_unknown_emails(
    api_client: TestClient, db: Session, email_outbox: MemoryEmailSender
) -> None:
    make_user(db, email=EMAIL)
    known = api_client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    sent_after_known = len(email_outbox.sent)
    unknown = api_client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert sent_after_known == 1
    assert len(email_outbox.sent) == 1  # nothing sent for the unknown address


def test_password_reset_changes_password_and_revokes_sessions(
    api_client: TestClient, db: Session, email_outbox: MemoryEmailSender
) -> None:
    make_user(db, email=EMAIL)
    old_session = login(api_client).cookies.get(REFRESH_COOKIE)
    assert old_session

    api_client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    token = email_outbox.last_token()
    new_password = "a-brand-new-password-1"

    reset = api_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": new_password}
    )
    assert reset.status_code == 200
    assert login(api_client, password=PASSWORD).status_code == 401
    assert login(api_client, password=new_password).status_code == 200
    assert refresh_with(api_client, old_session).status_code == 401  # "log out everywhere"

    again = api_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": "another-password-9"}
    )
    assert again.status_code == 400  # single use


def test_expired_reset_token_is_rejected(api_client: TestClient, db: Session) -> None:
    user = make_user(db)
    raw = "r" * 48
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    db.commit()
    response = api_client.post(
        "/api/v1/auth/reset-password", json={"token": raw, "new_password": "valid-new-password"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_token"


def test_newer_reset_request_invalidates_the_older_token(
    api_client: TestClient, db: Session, email_outbox: MemoryEmailSender
) -> None:
    make_user(db, email=EMAIL)
    api_client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    first = email_outbox.last_token()
    api_client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    second = email_outbox.last_token()

    payload = {"new_password": "valid-new-password"}
    assert (
        api_client.post("/api/v1/auth/reset-password", json={"token": first, **payload}).status_code
        == 400
    )
    assert (
        api_client.post(
            "/api/v1/auth/reset-password", json={"token": second, **payload}
        ).status_code
        == 200
    )


# --------------------------------------------------------------------------- rate limiting


def test_login_attempts_are_rate_limited_per_account(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.main import create_app

    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS", "3")
    get_settings.cache_clear()
    limited_app = create_app()
    override_db(limited_app, db)
    make_user(db, email=EMAIL)

    with TestClient(limited_app) as client:
        for _ in range(3):
            assert login(client, password="wrong-password-123").status_code == 401
        blocked = login(client, password="wrong-password-123")
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limited"
        assert int(blocked.headers["retry-after"]) >= 1
        # Another account is unaffected by this account's limit.
        assert login(client, email="other@example.com").status_code == 401
