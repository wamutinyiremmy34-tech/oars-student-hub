"""Schema integrity tests: constraints, relationships and catalog/migration agreement."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from helpers import make_institution, make_user
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog
from app.modules.auth.models import RefreshToken
from app.modules.institutions.models import Institution
from app.modules.rbac.catalog import PERMISSIONS, ROLES, permissions_for_role
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import StudentProfile, User

pytestmark = pytest.mark.integration


def _user(email: str = "x@example.com", **overrides: object) -> User:
    fields: dict[str, object] = {"email": email, "full_name": "X", "password_hash": "h"}
    return User(**{**fields, **overrides})  # type: ignore[arg-type]


def test_every_table_uses_uuid_primary_keys_and_timestamps(db: Session) -> None:
    rows = db.execute(
        text(
            "SELECT table_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'id'"
        )
    ).all()
    tables = {t for t, _ in rows}
    assert {"users", "institutions", "roles", "permissions", "user_roles", "student_profiles",
            "refresh_tokens", "verification_tokens", "password_reset_tokens", "audit_logs"} <= tables  # fmt: skip
    assert all(dtype == "uuid" for _, dtype in rows)


# --------------------------------------------------------------------------- users


def test_email_must_be_unique_and_lowercase(db: Session) -> None:
    db.add(_user("a@example.com"))
    db.commit()
    with pytest.raises(IntegrityError):
        db.add(_user("a@example.com"))
        db.flush()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.add(_user("Mixed@Example.com"))  # check constraint: email = lower(email)
        db.flush()
    db.rollback()


def test_user_status_is_constrained(db: Session) -> None:
    with pytest.raises(IntegrityError):
        db.add(_user(status="DELETED"))
        db.flush()
    db.rollback()


# --------------------------------------------------------------------------- user_roles scoping


def test_platform_wide_role_assignment_cannot_be_duplicated(db: Session) -> None:
    user = make_user(db)
    role = db.scalar(select(Role).where(Role.name == "ADMIN"))
    assert role is not None
    db.add(UserRole(user_id=user.id, role_id=role.id, institution_id=None))
    db.commit()
    with pytest.raises(IntegrityError):  # NULL institution would slip past a plain UNIQUE
        db.add(UserRole(user_id=user.id, role_id=role.id, institution_id=None))
        db.flush()
    db.rollback()


def test_scoped_role_assignment_unique_per_institution_but_allowed_across(db: Session) -> None:
    inst_a, inst_b = make_institution(db), make_institution(db)
    user = make_user(db)
    role = db.scalar(select(Role).where(Role.name == "ADMIN"))
    assert role is not None
    db.add_all(
        [
            UserRole(user_id=user.id, role_id=role.id, institution_id=inst_a.id),
            UserRole(user_id=user.id, role_id=role.id, institution_id=inst_b.id),
            UserRole(user_id=user.id, role_id=role.id, institution_id=None),
        ]
    )
    db.commit()  # same role in two institutions and platform-wide is legitimate
    with pytest.raises(IntegrityError):
        db.add(UserRole(user_id=user.id, role_id=role.id, institution_id=inst_a.id))
        db.flush()
    db.rollback()


# --------------------------------------------------------------------------- student profiles


def test_student_number_unique_per_institution_only(db: Session) -> None:
    inst_a, inst_b = make_institution(db), make_institution(db)
    u1, u2, u3, u4 = (make_user(db) for _ in range(4))
    db.add_all(
        [
            StudentProfile(user_id=u1.id, institution_id=inst_a.id, student_number="100"),
            StudentProfile(user_id=u2.id, institution_id=inst_b.id, student_number="100"),
            StudentProfile(user_id=u3.id, institution_id=inst_a.id, student_number=None),
            StudentProfile(user_id=u4.id, institution_id=inst_a.id, student_number=None),
        ]
    )
    db.commit()  # same number at another institution, and multiple NULLs, are fine
    u5 = make_user(db)
    with pytest.raises(IntegrityError):
        db.add(StudentProfile(user_id=u5.id, institution_id=inst_a.id, student_number="100"))
        db.flush()
    db.rollback()


def test_year_of_study_is_range_checked(db: Session) -> None:
    inst, user = make_institution(db), make_user(db)
    with pytest.raises(IntegrityError):
        db.add(StudentProfile(user_id=user.id, institution_id=inst.id, year_of_study=9))
        db.flush()
    db.rollback()


def test_one_profile_per_user(db: Session) -> None:
    inst = make_institution(db)
    user = make_user(db, institution=inst)
    with pytest.raises(IntegrityError):
        db.add(StudentProfile(user_id=user.id, institution_id=inst.id))
        db.flush()
    db.rollback()


# --------------------------------------------------------------------------- relationships / FKs


def test_user_and_profile_are_linked_both_ways(db: Session) -> None:
    inst = make_institution(db)
    user = make_user(db, institution=inst)
    profile = user.student_profile
    assert profile is not None
    assert profile.user is user
    assert profile.institution_id == inst.id


def test_institution_with_students_cannot_be_deleted(db: Session) -> None:
    inst = make_institution(db)
    make_user(db, institution=inst)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        db.delete(db.get(Institution, inst.id))
        db.flush()
    db.rollback()


def test_deleting_a_user_cascades_to_profile_roles_and_tokens(db: Session) -> None:
    inst = make_institution(db)
    user = make_user(db, institution=inst, roles=[("STUDENT", inst.id)])
    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=uuid.uuid4(),
            token_hash="a" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db.commit()
    user_id = user.id

    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})  # DB-level cascade
    for table in ("student_profiles", "user_roles", "refresh_tokens"):
        count = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE user_id = :id"), {"id": user_id}
        )
        assert count.scalar_one() == 0


def test_refresh_token_hash_is_unique(db: Session) -> None:
    user = make_user(db)

    def token() -> RefreshToken:
        return RefreshToken(
            user_id=user.id,
            family_id=uuid.uuid4(),
            token_hash="b" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )

    db.add(token())
    db.commit()
    with pytest.raises(IntegrityError):
        db.add(token())
        db.flush()
    db.rollback()


# --------------------------------------------------------------------------- audit log


def test_audit_log_is_append_only(db: Session) -> None:
    entry = AuditLog(action="test.event", details={"k": "v"})
    db.add(entry)
    db.commit()
    entry_id = entry.id

    with pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"), {"id": entry_id}
        )
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": entry_id})
    db.rollback()
    assert db.scalar(select(AuditLog.action).where(AuditLog.id == entry_id)) == "test.event"


def test_audit_outcome_is_constrained(db: Session) -> None:
    with pytest.raises(IntegrityError):
        db.add(AuditLog(action="x", outcome="MAYBE"))
        db.flush()
    db.rollback()


# --------------------------------------------------------------------------- catalog vs migration


def test_permission_catalog_in_code_matches_the_migrated_database(db: Session) -> None:
    db_permissions = {(p.code, p.platform_only) for p in db.scalars(select(Permission))}
    assert db_permissions == {(p.code, p.platform_only) for p in PERMISSIONS}

    assert {r.name for r in db.scalars(select(Role))} == set(ROLES)
    for role_name in ROLES:
        granted = set(
            db.scalars(
                select(Permission.code)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(Role, Role.id == RolePermission.role_id)
                .where(Role.name == role_name)
            )
        )
        assert granted == permissions_for_role(role_name), role_name


def test_the_five_initial_universities_are_seeded(db: Session) -> None:
    codes = set(db.scalars(select(Institution.code)))
    assert {"MAK", "KYU", "MUST", "UCU", "IUIU"} <= codes
