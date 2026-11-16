"""Academic catalogue: public reads and institution-scoped administration (permission catalog:manage)."""

import uuid
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError, ConflictError, NotFoundError
from app.core.http import RequestMeta
from app.modules.academic import schemas
from app.modules.academic.models import Course, Department, Faculty, Program, ProgramCourse
from app.modules.audit import service as audit
from app.modules.rbac.principal import Principal

M = TypeVar("M", Faculty, Department, Program, Course)
MANAGE = "catalog:manage"


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --------------------------------------------------------------------------- public reads


def list_faculties(db: Session, institution_id: uuid.UUID) -> list[Faculty]:
    stmt = select(Faculty).where(
        Faculty.institution_id == institution_id, Faculty.is_active.is_(True)
    )
    return list(db.scalars(stmt.order_by(Faculty.name)))


def list_departments(db: Session, faculty_id: uuid.UUID) -> list[Department]:
    stmt = select(Department).where(
        Department.faculty_id == faculty_id, Department.is_active.is_(True)
    )
    return list(db.scalars(stmt.order_by(Department.name)))


def list_programs(
    db: Session,
    institution_id: uuid.UUID,
    faculty_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
) -> list[Program]:
    stmt = select(Program).where(
        Program.institution_id == institution_id, Program.is_active.is_(True)
    )
    if faculty_id:
        stmt = stmt.where(Program.faculty_id == faculty_id)
    if department_id:
        stmt = stmt.where(Program.department_id == department_id)
    return list(db.scalars(stmt.order_by(Program.name, Program.level)))


def list_courses(
    db: Session,
    *,
    institution_id: uuid.UUID,
    faculty_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
    program_id: uuid.UUID | None,
    q: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Course], int]:
    stmt = select(Course).where(Course.institution_id == institution_id, Course.is_active.is_(True))
    if faculty_id:
        stmt = stmt.where(Course.faculty_id == faculty_id)
    if department_id:
        stmt = stmt.where(Course.department_id == department_id)
    if program_id:
        linked = select(ProgramCourse.course_id).where(ProgramCourse.program_id == program_id)
        stmt = stmt.where(Course.id.in_(linked))
    if q:
        pattern = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(
            Course.code.ilike(pattern, escape="\\") | Course.title.ilike(pattern, escape="\\")
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Course.code).limit(page_size).offset((page - 1) * page_size))
    return list(rows), total


# --------------------------------------------------------------------------- administration helpers


def _manageable(db: Session, principal: Principal, model: type[M], object_id: uuid.UUID) -> M:
    """Objects outside the caller's institution scope look like they do not exist (no id probing)."""
    obj = db.get(model, object_id)
    if obj is None or not principal.can(MANAGE, obj.institution_id):
        raise NotFoundError("Not found.")
    return obj


def _commit_unique(db: Session, what: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            f"A {what} with those details already exists.", code="already_exists"
        ) from exc


def _audit(db: Session, principal: Principal, action: str, obj: Any, meta: RequestMeta) -> None:
    audit.record(
        db,
        action=action,
        actor_user_id=principal.user.id,
        target_type=type(obj).__name__.lower(),
        target_id=str(obj.id),
        institution_id=obj.institution_id,
        meta=meta,
    )


def _apply(obj: Any, patch: Any) -> None:
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)


def _faculty_in_institution(
    db: Session, faculty_id: uuid.UUID, institution_id: uuid.UUID
) -> Faculty:
    faculty = db.get(Faculty, faculty_id)
    if faculty is None or faculty.institution_id != institution_id:
        raise BadRequestError("Unknown faculty for this institution.", code="invalid_faculty")
    return faculty


def _check_department(db: Session, department_id: uuid.UUID | None, faculty_id: uuid.UUID) -> None:
    if department_id is None:
        return
    department = db.get(Department, department_id)
    if department is None or department.faculty_id != faculty_id:
        raise BadRequestError(
            "The department does not belong to that faculty.", code="invalid_department"
        )


# --------------------------------------------------------------------------- mutations


def create_faculty(
    db: Session, principal: Principal, data: schemas.FacultyIn, meta: RequestMeta
) -> Faculty:
    principal.require(MANAGE, data.institution_id)
    faculty = Faculty(**data.model_dump())
    db.add(faculty)
    db.flush()
    _audit(db, principal, "catalog.faculty_created", faculty, meta)
    _commit_unique(db, "faculty")
    return faculty


def update_faculty(
    db: Session,
    principal: Principal,
    faculty_id: uuid.UUID,
    patch: schemas.FacultyPatch,
    meta: RequestMeta,
) -> Faculty:
    faculty = _manageable(db, principal, Faculty, faculty_id)
    _apply(faculty, patch)
    _audit(db, principal, "catalog.faculty_updated", faculty, meta)
    _commit_unique(db, "faculty")
    return faculty


def create_department(
    db: Session, principal: Principal, data: schemas.DepartmentIn, meta: RequestMeta
) -> Department:
    faculty = db.get(Faculty, data.faculty_id)
    if faculty is None or not principal.can(MANAGE, faculty.institution_id):
        raise NotFoundError("Faculty not found.")
    department = Department(institution_id=faculty.institution_id, **data.model_dump())
    db.add(department)
    db.flush()
    _audit(db, principal, "catalog.department_created", department, meta)
    _commit_unique(db, "department")
    return department


def update_department(
    db: Session,
    principal: Principal,
    department_id: uuid.UUID,
    patch: schemas.DepartmentPatch,
    meta: RequestMeta,
) -> Department:
    department = _manageable(db, principal, Department, department_id)
    _apply(department, patch)
    _audit(db, principal, "catalog.department_updated", department, meta)
    _commit_unique(db, "department")
    return department


def create_program(
    db: Session, principal: Principal, data: schemas.ProgramIn, meta: RequestMeta
) -> Program:
    faculty = db.get(Faculty, data.faculty_id)
    if faculty is None or not principal.can(MANAGE, faculty.institution_id):
        raise NotFoundError("Faculty not found.")
    _check_department(db, data.department_id, faculty.id)
    program = Program(institution_id=faculty.institution_id, **data.model_dump())
    db.add(program)
    db.flush()
    _audit(db, principal, "catalog.program_created", program, meta)
    _commit_unique(db, "program")
    return program


def update_program(
    db: Session,
    principal: Principal,
    program_id: uuid.UUID,
    patch: schemas.ProgramPatch,
    meta: RequestMeta,
) -> Program:
    program = _manageable(db, principal, Program, program_id)
    _apply(program, patch)
    _audit(db, principal, "catalog.program_updated", program, meta)
    _commit_unique(db, "program")
    return program


def create_course(
    db: Session, principal: Principal, data: schemas.CourseIn, meta: RequestMeta
) -> Course:
    faculty = db.get(Faculty, data.faculty_id)
    if faculty is None or not principal.can(MANAGE, faculty.institution_id):
        raise NotFoundError("Faculty not found.")
    _check_department(db, data.department_id, faculty.id)
    fields = data.model_dump()
    fields["code"] = data.code.strip().upper()
    course = Course(institution_id=faculty.institution_id, **fields)
    db.add(course)
    db.flush()
    _audit(db, principal, "catalog.course_created", course, meta)
    _commit_unique(db, "course")
    return course


def update_course(
    db: Session,
    principal: Principal,
    course_id: uuid.UUID,
    patch: schemas.CoursePatch,
    meta: RequestMeta,
) -> Course:
    course = _manageable(db, principal, Course, course_id)
    _apply(course, patch)
    _audit(db, principal, "catalog.course_updated", course, meta)
    _commit_unique(db, "course")
    return course


def link_course_to_program(
    db: Session,
    principal: Principal,
    program_id: uuid.UUID,
    data: schemas.ProgramCourseIn,
    meta: RequestMeta,
) -> ProgramCourse:
    program = _manageable(db, principal, Program, program_id)
    course = db.get(Course, data.course_id)
    if course is None or course.institution_id != program.institution_id:
        raise BadRequestError(
            "That course belongs to a different institution.", code="invalid_course"
        )
    link = ProgramCourse(
        program_id=program.id,
        course_id=course.id,
        institution_id=program.institution_id,
        year_of_study=data.year_of_study,
        semester=data.semester,
    )
    db.add(link)
    audit.record(
        db,
        action="catalog.program_course_linked",
        actor_user_id=principal.user.id,
        target_type="program",
        target_id=str(program.id),
        institution_id=program.institution_id,
        details={"course_id": str(course.id)},
        meta=meta,
    )
    _commit_unique(db, "program-course link")
    return link
