import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession
from app.core.http import RequestMetaDep
from app.core.responses import Envelope, ok
from app.modules.academic import schemas, service
from app.modules.auth.deps import require_permission
from app.modules.rbac.principal import Principal

faculties_router = APIRouter(prefix="/faculties", tags=["academic"])
departments_router = APIRouter(prefix="/departments", tags=["academic"])
programs_router = APIRouter(prefix="/programs", tags=["academic"])
courses_router = APIRouter(prefix="/courses", tags=["academic"])

CatalogAdmin = Annotated[Principal, Depends(require_permission("catalog:manage"))]


def _out(model, obj):  # type: ignore[no-untyped-def]
    return model.model_validate(obj, from_attributes=True)


# ------------------------------------------------------------------ faculties
@faculties_router.get("", response_model=Envelope[list[schemas.FacultyOut]])
def list_faculties(db: DbSession, institution_id: uuid.UUID) -> Envelope[list[schemas.FacultyOut]]:
    return ok([_out(schemas.FacultyOut, f) for f in service.list_faculties(db, institution_id)])


@faculties_router.post("", status_code=201, response_model=Envelope[schemas.FacultyOut])
def create_faculty(
    body: schemas.FacultyIn, db: DbSession, meta: RequestMetaDep, principal: CatalogAdmin
) -> Envelope[schemas.FacultyOut]:
    return ok(_out(schemas.FacultyOut, service.create_faculty(db, principal, body, meta)))


@faculties_router.patch("/{faculty_id}", response_model=Envelope[schemas.FacultyOut])
def update_faculty(
    faculty_id: uuid.UUID,
    body: schemas.FacultyPatch,
    db: DbSession,
    meta: RequestMetaDep,
    principal: CatalogAdmin,
) -> Envelope[schemas.FacultyOut]:
    return ok(
        _out(schemas.FacultyOut, service.update_faculty(db, principal, faculty_id, body, meta))
    )


# ------------------------------------------------------------------ departments
@departments_router.get("", response_model=Envelope[list[schemas.DepartmentOut]])
def list_departments(db: DbSession, faculty_id: uuid.UUID) -> Envelope[list[schemas.DepartmentOut]]:
    return ok([_out(schemas.DepartmentOut, d) for d in service.list_departments(db, faculty_id)])


@departments_router.post("", status_code=201, response_model=Envelope[schemas.DepartmentOut])
def create_department(
    body: schemas.DepartmentIn, db: DbSession, meta: RequestMetaDep, principal: CatalogAdmin
) -> Envelope[schemas.DepartmentOut]:
    return ok(_out(schemas.DepartmentOut, service.create_department(db, principal, body, meta)))


@departments_router.patch("/{department_id}", response_model=Envelope[schemas.DepartmentOut])
def update_department(
    department_id: uuid.UUID,
    body: schemas.DepartmentPatch,
    db: DbSession,
    meta: RequestMetaDep,
    principal: CatalogAdmin,
) -> Envelope[schemas.DepartmentOut]:
    return ok(
        _out(
            schemas.DepartmentOut,
            service.update_department(db, principal, department_id, body, meta),
        )
    )


# ------------------------------------------------------------------ programs
@programs_router.get("", response_model=Envelope[list[schemas.ProgramOut]])
def list_programs(
    db: DbSession,
    institution_id: uuid.UUID,
    faculty_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
) -> Envelope[list[schemas.ProgramOut]]:
    rows = service.list_programs(db, institution_id, faculty_id, department_id)
    return ok([_out(schemas.ProgramOut, p) for p in rows])


@programs_router.post("", status_code=201, response_model=Envelope[schemas.ProgramOut])
def create_program(
    body: schemas.ProgramIn, db: DbSession, meta: RequestMetaDep, principal: CatalogAdmin
) -> Envelope[schemas.ProgramOut]:
    return ok(_out(schemas.ProgramOut, service.create_program(db, principal, body, meta)))


@programs_router.patch("/{program_id}", response_model=Envelope[schemas.ProgramOut])
def update_program(
    program_id: uuid.UUID,
    body: schemas.ProgramPatch,
    db: DbSession,
    meta: RequestMetaDep,
    principal: CatalogAdmin,
) -> Envelope[schemas.ProgramOut]:
    return ok(
        _out(schemas.ProgramOut, service.update_program(db, principal, program_id, body, meta))
    )


@programs_router.post(
    "/{program_id}/courses", status_code=201, response_model=Envelope[schemas.ProgramCourseIn]
)
def link_course(
    program_id: uuid.UUID,
    body: schemas.ProgramCourseIn,
    db: DbSession,
    meta: RequestMetaDep,
    principal: CatalogAdmin,
) -> Envelope[schemas.ProgramCourseIn]:
    link = service.link_course_to_program(db, principal, program_id, body, meta)
    return ok(
        schemas.ProgramCourseIn(
            course_id=link.course_id, year_of_study=link.year_of_study, semester=link.semester
        )
    )


# ------------------------------------------------------------------ courses
@courses_router.get("", response_model=Envelope[list[schemas.CourseOut]])
def list_courses(
    db: DbSession,
    institution_id: uuid.UUID,
    faculty_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    program_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[list[schemas.CourseOut]]:
    rows, total = service.list_courses(
        db, institution_id=institution_id, faculty_id=faculty_id, department_id=department_id,
        program_id=program_id, q=q, page=page, page_size=page_size,
    )  # fmt: skip
    return ok(
        [_out(schemas.CourseOut, c) for c in rows],
        meta={"page": page, "page_size": page_size, "total": total},
    )


@courses_router.post("", status_code=201, response_model=Envelope[schemas.CourseOut])
def create_course(
    body: schemas.CourseIn, db: DbSession, meta: RequestMetaDep, principal: CatalogAdmin
) -> Envelope[schemas.CourseOut]:
    return ok(_out(schemas.CourseOut, service.create_course(db, principal, body, meta)))


@courses_router.patch("/{course_id}", response_model=Envelope[schemas.CourseOut])
def update_course(
    course_id: uuid.UUID,
    body: schemas.CoursePatch,
    db: DbSession,
    meta: RequestMetaDep,
    principal: CatalogAdmin,
) -> Envelope[schemas.CourseOut]:
    return ok(_out(schemas.CourseOut, service.update_course(db, principal, course_id, body, meta)))
