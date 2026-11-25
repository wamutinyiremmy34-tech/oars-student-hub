"""Response schemas are explicit allow-lists: password_hash and token fields can never serialise out."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints

from app.modules.users.models import StudentProfile, User


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    status: str
    email_verified: bool
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            status=user.status,
            email_verified=user.email_verified_at is not None,
            created_at=user.created_at,
        )


class StudentProfileOut(BaseModel):
    institution_id: uuid.UUID
    program_id: uuid.UUID | None
    student_number: str | None
    year_of_study: int | None

    @classmethod
    def from_profile(cls, profile: StudentProfile) -> Self:
        return cls(
            institution_id=profile.institution_id,
            program_id=profile.program_id,
            student_number=profile.student_number,
            year_of_study=profile.year_of_study,
        )


class RoleAssignmentOut(BaseModel):
    role: str
    institution_id: uuid.UUID | None


class GrantOut(BaseModel):
    permission: str
    institution_id: uuid.UUID | None


class MeOut(BaseModel):
    """What the UI may use to tailor navigation. The backend re-checks every permission on every request."""

    user: UserPublic
    student_profile: StudentProfileOut | None
    roles: list[RoleAssignmentOut]
    permissions: list[GrantOut]


class UserAdminOut(BaseModel):
    user: UserPublic
    suspended_at: datetime | None
    suspended_reason: str | None
    institution_ids: list[uuid.UUID]
    roles: list[RoleAssignmentOut]


class ProfilePatch(BaseModel):
    """Fields a user may update on their own profile.  Email and role cannot be changed here."""

    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = Field(
        default=None,
        description="Phone number. Send an empty string to clear.",
    )


class SuspendIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]


class GrantRoleIn(BaseModel):
    role: Annotated[str, StringConstraints(pattern=r"^[A-Z_]{3,50}$")]
    institution_id: uuid.UUID | None = Field(
        default=None,
        description="Omit for a platform-wide role; set to scope the role to one institution.",
    )
