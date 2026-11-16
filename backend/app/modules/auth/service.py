"""Authentication logic: registration, login, refresh rotation, logout, email verification, reset."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    UnauthorizedError,
)
from app.core.http import RequestMeta
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.modules.audit import service as audit
from app.modules.auth.models import PasswordResetToken, RefreshToken, VerificationToken
from app.modules.auth.schemas import RegisterIn
from app.modules.institutions.models import Institution
from app.modules.rbac.service import add_user_role, get_role
from app.modules.users.models import StudentProfile, User, UserStatus
from app.providers.email import EmailMessage, EmailSender

logger = logging.getLogger(__name__)

_INVALID_CREDENTIALS = "Invalid email or password."


@dataclass(frozen=True)
class IssuedSession:
    user: User
    access_token: str
    refresh_token: str
    expires_in: int


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(UTC)


@lru_cache
def _dummy_password_hash() -> str:
    # Verified against when the email is unknown so response time does not reveal which emails exist.
    return hash_password("not-a-real-password-used-only-for-timing")


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return name if isinstance(name, str) else None


def _safe_send(sender: EmailSender, message: EmailMessage) -> None:
    # A mail outage must not turn a successful registration/reset request into an error.
    try:
        sender.send(message)
    except Exception:
        logger.exception("email_send_failed")


# --------------------------------------------------------------------------- refresh tokens


def _issue_refresh_token(
    db: Session, *, user_id: uuid.UUID, family_id: uuid.UUID, meta: RequestMeta
) -> str:
    raw = generate_opaque_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_token(raw),
            expires_at=_now() + timedelta(days=get_settings().refresh_token_ttl_days),
            user_agent=meta.user_agent,
            ip_address=meta.ip,
        )
    )
    return raw


def revoke_family(db: Session, family_id: uuid.UUID, *, reason: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now(), revoked_reason=reason),
        execution_options={"synchronize_session": False},
    )


def revoke_all_for_user(db: Session, user_id: uuid.UUID, *, reason: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now(), revoked_reason=reason),
        execution_options={"synchronize_session": False},
    )


def _new_session(db: Session, user: User, meta: RequestMeta, family_id: uuid.UUID) -> IssuedSession:
    settings = get_settings()
    raw_refresh = _issue_refresh_token(db, user_id=user.id, family_id=family_id, meta=meta)
    return IssuedSession(
        user=user,
        access_token=create_access_token(str(user.id)),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


# --------------------------------------------------------------------------- registration


def register_student(
    db: Session, data: RegisterIn, *, meta: RequestMeta, email_sender: EmailSender
) -> User:
    settings = get_settings()
    email = normalize_email(data.email)

    institution = db.get(Institution, data.institution_id)
    if institution is None or not institution.is_active:
        raise BadRequestError("Please choose a valid institution.", code="invalid_institution")

    # Registration necessarily reveals whether an email is taken (the user must be told).
    # Login and password-reset endpoints do not.
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise ConflictError("An account with this email already exists.", code="email_taken")

    user = User(
        email=email,
        full_name=data.full_name,
        phone=data.phone,
        password_hash=hash_password(data.password),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            StudentProfile(
                user_id=user.id, institution_id=institution.id, student_number=data.student_number
            )
        )
        db.flush()  # surface a duplicate student number here, not inside add_user_role
        add_user_role(
            db,
            user_id=user.id,
            role=get_role(db, "STUDENT"),
            institution_id=institution.id,
            granted_by=None,
        )
        raw_token = generate_opaque_token()
        db.add(
            VerificationToken(
                user_id=user.id,
                purpose="EMAIL",
                token_hash=hash_token(raw_token),
                expires_at=_now() + timedelta(hours=settings.email_verification_ttl_hours),
            )
        )
        audit.record(
            db,
            action="auth.registered",
            actor_user_id=user.id,
            target_type="user",
            target_id=str(user.id),
            institution_id=institution.id,
            meta=meta,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        name = _constraint_name(exc)
        if name == "uq_users_email":
            raise ConflictError(
                "An account with this email already exists.", code="email_taken"
            ) from exc
        if name == "uq_student_profiles_institution_student_number":
            raise ConflictError(
                "That student number is already registered at this institution.",
                code="student_number_taken",
            ) from exc
        raise

    link = f"{settings.public_app_url}/verify-email?token={raw_token}"
    _safe_send(
        email_sender,
        EmailMessage(
            to=user.email,
            subject="Verify your OARS account",
            body=f"Welcome to OARS Student Solutions.\n\nVerify your email: {link}\n",
        ),
    )
    return user


# --------------------------------------------------------------------------- login / refresh / logout


def login(db: Session, *, email: str, password: str, meta: RequestMeta) -> IssuedSession:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))

    if user is None:
        verify_password(password, _dummy_password_hash())
        audit.record(
            db,
            action="auth.login_failed",
            outcome="FAILURE",
            details={"reason": "unknown_email"},
            meta=meta,
        )
        db.commit()
        raise UnauthorizedError(_INVALID_CREDENTIALS, code="invalid_credentials")

    if not verify_password(password, user.password_hash):
        audit.record(
            db,
            action="auth.login_failed",
            outcome="FAILURE",
            actor_user_id=user.id,
            details={"reason": "bad_password"},
            meta=meta,
        )
        db.commit()
        raise UnauthorizedError(_INVALID_CREDENTIALS, code="invalid_credentials")

    # Only reached with the correct password, so this does not let strangers probe account states.
    if user.status != UserStatus.ACTIVE:
        audit.record(
            db, action="auth.login_denied", outcome="DENIED", actor_user_id=user.id, meta=meta
        )
        db.commit()
        raise ForbiddenError("This account has been suspended.", code="account_suspended")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = _now()
    issued = _new_session(db, user, meta, family_id=uuid.uuid4())
    audit.record(db, action="auth.login", actor_user_id=user.id, meta=meta)
    db.commit()
    return issued


def refresh_session(db: Session, *, raw_token: str, meta: RequestMeta) -> IssuedSession:
    invalid = UnauthorizedError("Your session has expired.", code="invalid_refresh_token")
    row = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    if row is None:
        raise invalid

    now = _now()
    if row.revoked_at is not None:
        if row.revoked_reason == "rotated":
            # A token that was already exchanged is being replayed: assume it was stolen and kill
            # the whole session family, including the newest token.
            revoke_family(db, row.family_id, reason="reuse")
            audit.record(
                db,
                action="auth.refresh_reuse_detected",
                outcome="DENIED",
                actor_user_id=row.user_id,
                meta=meta,
            )
            db.commit()
        raise invalid

    if row.expires_at <= now:
        raise invalid

    user = db.get(User, row.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        revoke_family(db, row.family_id, reason="suspended")
        db.commit()
        raise invalid

    row.revoked_at = now
    row.revoked_reason = "rotated"
    issued = _new_session(db, user, meta, family_id=row.family_id)
    db.commit()
    return issued


def logout(db: Session, *, raw_token: str, meta: RequestMeta) -> None:
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is None:
        return  # Idempotent: logging out with an unknown/expired cookie is not an error.
    revoke_family(db, row.family_id, reason="logout")
    audit.record(db, action="auth.logout", actor_user_id=row.user_id, meta=meta)
    db.commit()


# --------------------------------------------------------------------------- email verification


def verify_email(db: Session, *, raw_token: str, meta: RequestMeta) -> None:
    row = db.scalar(
        select(VerificationToken)
        .where(VerificationToken.token_hash == hash_token(raw_token))
        .where(VerificationToken.purpose == "EMAIL")
        .with_for_update()
    )
    now = _now()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise BadRequestError(
            "This verification link is invalid or has expired.", code="invalid_token"
        )
    row.used_at = now
    user = db.get(User, row.user_id)
    if user is not None and user.email_verified_at is None:
        user.email_verified_at = now
    audit.record(db, action="auth.email_verified", actor_user_id=row.user_id, meta=meta)
    db.commit()


# --------------------------------------------------------------------------- password reset


def request_password_reset(
    db: Session, *, email: str, meta: RequestMeta, email_sender: EmailSender
) -> None:
    """Always returns normally so callers can give the same response whether or not the email exists."""
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None or user.status != UserStatus.ACTIVE:
        return

    now = _now()
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now),
        execution_options={"synchronize_session": False},
    )
    raw = generate_opaque_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    audit.record(db, action="auth.password_reset_requested", actor_user_id=user.id, meta=meta)
    db.commit()

    link = f"{settings.public_app_url}/reset-password?token={raw}"
    _safe_send(
        email_sender,
        EmailMessage(
            to=user.email,
            subject="Reset your OARS password",
            body=f"Reset your password: {link}\n\nIf you did not ask for this, ignore this email.\n",
        ),
    )


def reset_password(db: Session, *, raw_token: str, new_password: str, meta: RequestMeta) -> None:
    row = db.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    now = _now()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise BadRequestError("This reset link is invalid or has expired.", code="invalid_token")
    user = db.get(User, row.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise BadRequestError("This reset link is invalid or has expired.", code="invalid_token")

    user.password_hash = hash_password(new_password)
    row.used_at = now
    # A reset is a "log out everywhere": every session may belong to whoever knew the old password.
    revoke_all_for_user(db, user.id, reason="password_reset")
    audit.record(db, action="auth.password_reset", actor_user_id=user.id, meta=meta)
    db.commit()
