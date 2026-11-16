import uuid
from typing import Annotated

from pydantic import BaseModel, StringConstraints


class InstitutionPublic(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    slug: str


class InstitutionIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=20)]


class InstitutionPatch(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
        | None
    ) = None
    is_active: bool | None = None
