import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserStatus:
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("status IN ('ACTIVE', 'SUSPENDED')", name="status_valid"),
        Index("ix_users_status", "status"),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), server_default=UserStatus.ACTIVE)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_reason: Mapped[str | None] = mapped_column(String(255))

    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )


class StudentProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_profiles"
    __table_args__ = (
        UniqueConstraint(
            "institution_id",
            "student_number",
            name="uq_student_profiles_institution_student_number",
        ),
        CheckConstraint(
            "year_of_study IS NULL OR year_of_study BETWEEN 1 AND 8", name="year_of_study_range"
        ),
        Index("ix_student_profiles_institution_id", "institution_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT")
    )
    # The service layer checks the program belongs to the same institution as the profile.
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL")
    )
    student_number: Mapped[str | None] = mapped_column(String(50))
    year_of_study: Mapped[int | None] = mapped_column(SmallInteger)

    user: Mapped[User] = relationship(back_populates="student_profile")
