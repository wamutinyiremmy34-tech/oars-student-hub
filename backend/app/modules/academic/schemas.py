import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
ShortCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
CourseCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=30)]
FacultyKind = Literal["FACULTY", "SCHOOL", "COLLEGE", "INSTITUTE"]
ProgramLevel = Literal[
    "CERTIFICATE", "DIPLOMA", "BACHELORS", "POSTGRADUATE_DIPLOMA", "MASTERS", "PHD", "OTHER"
]


class FacultyIn(BaseModel):
    institution_id: uuid.UUID
    name: Name
    kind: FacultyKind = "FACULTY"
    code: ShortCode | None = None


class FacultyPatch(BaseModel):
    name: Name | None = None
    kind: FacultyKind | None = None
    code: ShortCode | None = None
    is_active: bool | None = None


class FacultyOut(BaseModel):
    id: uuid.UUID
    institution_id: uuid.UUID
    name: str
    kind: str
    code: str | None
    is_active: bool


class DepartmentIn(BaseModel):
    faculty_id: uuid.UUID
    name: Name
    code: ShortCode | None = None


class DepartmentPatch(BaseModel):
    name: Name | None = None
    code: ShortCode | None = None
    is_active: bool | None = None


class DepartmentOut(BaseModel):
    id: uuid.UUID
    institution_id: uuid.UUID
    faculty_id: uuid.UUID
    name: str
    code: str | None
    is_active: bool


class ProgramIn(BaseModel):
    faculty_id: uuid.UUID
    department_id: uuid.UUID | None = None
    name: Name
    code: CourseCode | None = None
    level: ProgramLevel = "BACHELORS"
    duration_years: int | None = Field(default=None, ge=1, le=8)


class ProgramPatch(BaseModel):
    name: Name | None = None
    code: CourseCode | None = None
    level: ProgramLevel | None = None
    duration_years: int | None = Field(default=None, ge=1, le=8)
    is_active: bool | None = None


class ProgramOut(BaseModel):
    id: uuid.UUID
    institution_id: uuid.UUID
    faculty_id: uuid.UUID
    department_id: uuid.UUID | None
    name: str
    code: str | None
    level: str
    duration_years: int | None
    is_active: bool


class CourseIn(BaseModel):
    faculty_id: uuid.UUID
    department_id: uuid.UUID | None = None
    code: CourseCode
    title: Name
    credit_units: int | None = Field(default=None, ge=0, le=30)


class CoursePatch(BaseModel):
    title: Name | None = None
    credit_units: int | None = Field(default=None, ge=0, le=30)
    is_active: bool | None = None


class CourseOut(BaseModel):
    id: uuid.UUID
    institution_id: uuid.UUID
    faculty_id: uuid.UUID
    department_id: uuid.UUID | None
    code: str
    title: str
    credit_units: int | None
    is_active: bool


class ProgramCourseIn(BaseModel):
    course_id: uuid.UUID
    year_of_study: int | None = Field(default=None, ge=1, le=8)
    semester: int | None = Field(default=None, ge=1, le=3)
