"""Academic hierarchy: Institution -> Faculty -> Department -> Program -> Course.

Universities differ in structure, so:
  * `faculties.kind` records what the institution calls the top-level unit (faculty, school, college, institute);
  * a program or course may sit directly under a faculty (department_id NULL);
  * programs <-> courses is many-to-many (program_courses).

Isolation is enforced by the DATABASE: every level carries institution_id and composite foreign keys
force a child's institution to equal its parent's. A department cannot point at another university's faculty,
and a course cannot be linked to another university's program, regardless of application bugs.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

FACULTY_KINDS = ("FACULTY", "SCHOOL", "COLLEGE", "INSTITUTE")
PROGRAM_LEVELS = (
    "CERTIFICATE", "DIPLOMA", "BACHELORS", "POSTGRADUATE_DIPLOMA", "MASTERS", "PHD", "OTHER",
)  # fmt: skip


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Faculty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "faculties"
    __table_args__ = (
        ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name="fk_faculties_institution_id_institutions",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("institution_id", "name", name="uq_faculties_institution_id_name"),
        UniqueConstraint("institution_id", "code", name="uq_faculties_institution_id_code"),
        UniqueConstraint("id", "institution_id", name="uq_faculties_id_institution_id"),
        CheckConstraint(_in("kind", FACULTY_KINDS), name="kind_valid"),
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), server_default="FACULTY")
    code: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["faculty_id", "institution_id"], ["faculties.id", "faculties.institution_id"],
            name="fk_departments_faculty_institution", ondelete="RESTRICT",
        ),
        UniqueConstraint("faculty_id", "name", name="uq_departments_faculty_id_name"),
        UniqueConstraint("id", "faculty_id", name="uq_departments_id_faculty_id"),
        Index("ix_departments_institution_id", "institution_id"),
    )  # fmt: skip

    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    faculty_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Program(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "programs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["faculty_id", "institution_id"], ["faculties.id", "faculties.institution_id"],
            name="fk_programs_faculty_institution", ondelete="RESTRICT",
        ),
        # department_id may be NULL (program directly under a faculty); when set it must belong to that faculty.
        ForeignKeyConstraint(
            ["department_id", "faculty_id"], ["departments.id", "departments.faculty_id"],
            name="fk_programs_department_faculty", ondelete="RESTRICT",
        ),
        UniqueConstraint("institution_id", "name", "level", name="uq_programs_institution_id_name_level"),
        UniqueConstraint("id", "institution_id", name="uq_programs_id_institution_id"),
        CheckConstraint(_in("level", PROGRAM_LEVELS), name="level_valid"),
        CheckConstraint(
            "duration_years IS NULL OR duration_years BETWEEN 1 AND 8", name="duration_years_range"
        ),
        Index("ix_programs_faculty_id", "faculty_id"),
    )  # fmt: skip

    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    faculty_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(30))
    level: Mapped[str] = mapped_column(String(25), server_default="BACHELORS")
    duration_years: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Course(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["faculty_id", "institution_id"], ["faculties.id", "faculties.institution_id"],
            name="fk_courses_faculty_institution", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["department_id", "faculty_id"], ["departments.id", "departments.faculty_id"],
            name="fk_courses_department_faculty", ondelete="RESTRICT",
        ),
        UniqueConstraint("institution_id", "code", name="uq_courses_institution_id_code"),
        UniqueConstraint("id", "institution_id", name="uq_courses_id_institution_id"),
        CheckConstraint("code = upper(code)", name="code_uppercase"),
        CheckConstraint("credit_units IS NULL OR credit_units BETWEEN 0 AND 30", name="credit_units_range"),
        Index("ix_courses_faculty_id", "faculty_id"),
        Index("ix_courses_department_id", "department_id"),
    )  # fmt: skip

    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    faculty_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    code: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    credit_units: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class ProgramCourse(Base):
    __tablename__ = "program_courses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["program_id", "institution_id"], ["programs.id", "programs.institution_id"],
            name="fk_program_courses_program_institution", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["course_id", "institution_id"], ["courses.id", "courses.institution_id"],
            name="fk_program_courses_course_institution", ondelete="CASCADE",
        ),
        CheckConstraint("year_of_study IS NULL OR year_of_study BETWEEN 1 AND 8", name="year_of_study_range"),
        CheckConstraint("semester IS NULL OR semester BETWEEN 1 AND 3", name="semester_range"),
        Index("ix_program_courses_course_id", "course_id"),
    )  # fmt: skip

    program_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    year_of_study: Mapped[int | None] = mapped_column(SmallInteger)
    semester: Mapped[int | None] = mapped_column(SmallInteger)
