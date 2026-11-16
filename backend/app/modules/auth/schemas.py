import uuid
from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints

from app.modules.users.schemas import UserPublic

# max_length bounds Argon2 work per request; min_length 10 follows current NIST/OWASP guidance for
# length over composition rules.
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Phone = Annotated[str, StringConstraints(pattern=r"^\+?[0-9]{9,15}$")]
StudentNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
OneTimeToken = Annotated[str, StringConstraints(min_length=20, max_length=200)]


class RegisterIn(BaseModel):
    email: EmailStr
    password: Password
    full_name: FullName
    institution_id: uuid.UUID
    student_number: StudentNumber | None = None
    phone: Phone | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class VerifyIn(BaseModel):
    token: OneTimeToken


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: OneTimeToken
    new_password: Password


class TokenOut(BaseModel):
    """The refresh token is NEVER in the body: it travels only in an HttpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterOut(BaseModel):
    user: UserPublic


class MessageOut(BaseModel):
    message: str
