"""PostgreSQL search over PUBLISHED resources: full-text on title+description, plus course code,
tag and title matching. No external search engine."""

from sqlalchemy import Select, case, exists, func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.modules.academic.models import Course, ProgramCourse
from app.modules.academic.service import escape_like
from app.modules.resources.models import (
    CourseResource,
    Resource,
    ResourceCategory,
    ResourceStatus,
    ResourceTag,
    Tag,
)
from app.modules.resources.schemas import SearchParams

# websearch_to_tsquery needs a regconfig as its first argument. A bound parameter would be sent as
# VARCHAR (no implicit cast to regconfig), so the constant configuration name is inlined.
_ENGLISH = literal_column("'english'")


def _course_filter(*conditions: object) -> object:
    return exists(
        select(1)
        .select_from(
            CourseResource.__table__.join(Course.__table__, Course.id == CourseResource.course_id)
        )
        .where(CourseResource.resource_id == Resource.id, *conditions)
    )


def _apply_filters(stmt: Select, p: SearchParams) -> Select:  # type: ignore[type-arg]
    if p.institution_id:
        stmt = stmt.where(Resource.institution_id == p.institution_id)
    if p.access:
        stmt = stmt.where(Resource.access_type == p.access)
    if p.academic_year:
        stmt = stmt.where(Resource.academic_year == p.academic_year)
    if p.category:
        stmt = stmt.where(
            Resource.category_id.in_(
                select(ResourceCategory.id).where(ResourceCategory.slug == p.category)
            )
        )
    if p.tag:
        stmt = stmt.where(
            exists(
                select(1)
                .select_from(
                    ResourceTag.__table__.join(Tag.__table__, Tag.id == ResourceTag.tag_id)
                )
                .where(ResourceTag.resource_id == Resource.id, Tag.name == p.tag.lower())
            )
        )
    if p.course_id:
        stmt = stmt.where(
            exists(
                select(1).where(
                    CourseResource.resource_id == Resource.id,
                    CourseResource.course_id == p.course_id,
                )
            )
        )
    if p.faculty_id:
        stmt = stmt.where(_course_filter(Course.faculty_id == p.faculty_id))
    if p.department_id:
        stmt = stmt.where(_course_filter(Course.department_id == p.department_id))
    if p.program_id:
        stmt = stmt.where(
            exists(
                select(1)
                .select_from(
                    CourseResource.__table__.join(
                        ProgramCourse.__table__, ProgramCourse.course_id == CourseResource.course_id
                    )
                )
                .where(
                    CourseResource.resource_id == Resource.id,
                    ProgramCourse.program_id == p.program_id,
                )
            )
        )
    return stmt


def search_resources(db: Session, p: SearchParams) -> tuple[list[Resource], int]:
    base = select(Resource).where(
        Resource.status == ResourceStatus.PUBLISHED
    )  # never anything else
    base = _apply_filters(base, p)

    rank = None
    if p.q:
        q = p.q
        tsquery = func.websearch_to_tsquery(_ENGLISH, q)
        like = f"%{escape_like(q)}%"
        compact = escape_like(q.replace(" ", "").upper())
        code_hit = exists(
            select(1)
            .select_from(
                CourseResource.__table__.join(
                    Course.__table__, Course.id == CourseResource.course_id
                )
            )
            .where(
                CourseResource.resource_id == Resource.id,
                func.replace(Course.code, " ", "").like(f"{compact}%", escape="\\"),
            )
        )
        tag_hit = exists(
            select(1)
            .select_from(ResourceTag.__table__.join(Tag.__table__, Tag.id == ResourceTag.tag_id))
            .where(ResourceTag.resource_id == Resource.id, Tag.name == q.lower())
        )
        title_hit = Resource.title.ilike(like, escape="\\")
        fts_hit = Resource.search_vector.op("@@")(tsquery)
        base = base.where(or_(fts_hit, title_hit, code_hit, tag_hit))
        rank = (
            func.coalesce(func.ts_rank_cd(Resource.search_vector, tsquery), 0)
            + case((title_hit, 0.5), else_=0)
            + case((code_hit, 1.0), else_=0)
            + case((tag_hit, 0.3), else_=0)
        )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    sort = p.sort or ("relevance" if p.q else "newest")
    if sort == "relevance" and rank is not None:
        ordering = [rank.desc(), Resource.published_at.desc(), Resource.id]
    elif sort == "title":
        ordering = [func.lower(Resource.title), Resource.id]
    else:
        ordering = [
            Resource.published_at.desc().nulls_last(),
            Resource.id,
        ]  # id breaks ties: stable paging

    rows = db.scalars(
        base.order_by(*ordering).limit(p.page_size).offset((p.page - 1) * p.page_size)
    )
    return list(rows), total
