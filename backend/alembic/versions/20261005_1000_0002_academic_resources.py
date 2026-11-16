"""Academic structure, resources, versions, entitlements, bookmarks, file metadata, download log.

Revision ID: 0002_academic_resources
Revises: 0001_identity
Create Date: 2026-10-05
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_academic_resources"
down_revision: str | None = "0001_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --- Frozen reference data for this revision ---
NEW_PERMISSIONS = [
    (
        "resource:review_own",
        "Review or publish one's own resources (separation-of-duties override)",
        False,
    ),
    ("catalog:manage", "Manage faculties, departments, programs and courses", False),
    ("category:manage", "Manage resource categories", True),
    ("entitlement:manage", "Grant and revoke access to premium resources", False),
]
CATEGORIES = [
    ("Notes", "notes", "Lecture and study notes", 10),
    ("Past papers", "past-papers", "Previous examination papers", 20),
    ("Handouts", "handouts", "Lecturer handouts and slides", 30),
    ("Study guides", "study-guides", "Revision guides and summaries", 40),
    ("Reference material", "reference-material", "Textbooks and reference documents", 50),
    (
        "Academic documents",
        "academic-documents",
        "Course outlines, guidelines and other documents",
        60,
    ),
]
SEARCH_VECTOR_SQL = (
    "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))"
)


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _bool(name: str, default: bool) -> sa.Column:
    return sa.Column(
        name, sa.Boolean(), server_default=sa.true() if default else sa.false(), nullable=False
    )


def _ts_clock(name: str) -> sa.Column:
    """Event-log time: the real moment of the event (now() would be the start of the transaction)."""
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("clock_timestamp()"),
        nullable=False,
    )


def upgrade() -> None:
    # ------------------------------------------------------------------ academic hierarchy
    op.create_table(
        "faculties",
        _id(), _uuid("institution_id"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), server_default="FACULTY", nullable=False),
        sa.Column("code", sa.String(20), nullable=True),
        _bool("is_active", True), _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_faculties")),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], name="fk_faculties_institution_id_institutions", ondelete="RESTRICT"),
        sa.UniqueConstraint("institution_id", "name", name="uq_faculties_institution_id_name"),
        sa.UniqueConstraint("institution_id", "code", name="uq_faculties_institution_id_code"),
        sa.UniqueConstraint("id", "institution_id", name="uq_faculties_id_institution_id"),
        sa.CheckConstraint("kind IN ('FACULTY', 'SCHOOL', 'COLLEGE', 'INSTITUTE')", name=op.f("ck_faculties_kind_valid")),
    )  # fmt: skip

    op.create_table(
        "departments",
        _id(), _uuid("institution_id"), _uuid("faculty_id"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(20), nullable=True),
        _bool("is_active", True), _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.ForeignKeyConstraint(["faculty_id", "institution_id"], ["faculties.id", "faculties.institution_id"], name="fk_departments_faculty_institution", ondelete="RESTRICT"),
        sa.UniqueConstraint("faculty_id", "name", name="uq_departments_faculty_id_name"),
        sa.UniqueConstraint("id", "faculty_id", name="uq_departments_id_faculty_id"),
    )  # fmt: skip
    op.create_index("ix_departments_institution_id", "departments", ["institution_id"])

    op.create_table(
        "programs",
        _id(), _uuid("institution_id"), _uuid("faculty_id"), _uuid("department_id", nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(30), nullable=True),
        sa.Column("level", sa.String(25), server_default="BACHELORS", nullable=False),
        sa.Column("duration_years", sa.SmallInteger(), nullable=True),
        _bool("is_active", True), _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_programs")),
        sa.ForeignKeyConstraint(["faculty_id", "institution_id"], ["faculties.id", "faculties.institution_id"], name="fk_programs_faculty_institution", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["department_id", "faculty_id"], ["departments.id", "departments.faculty_id"], name="fk_programs_department_faculty", ondelete="RESTRICT"),
        sa.UniqueConstraint("institution_id", "name", "level", name="uq_programs_institution_id_name_level"),
        sa.UniqueConstraint("id", "institution_id", name="uq_programs_id_institution_id"),
        sa.CheckConstraint("level IN ('CERTIFICATE', 'DIPLOMA', 'BACHELORS', 'POSTGRADUATE_DIPLOMA', 'MASTERS', 'PHD', 'OTHER')", name=op.f("ck_programs_level_valid")),
        sa.CheckConstraint("duration_years IS NULL OR duration_years BETWEEN 1 AND 8", name=op.f("ck_programs_duration_years_range")),
    )  # fmt: skip
    op.create_index("ix_programs_faculty_id", "programs", ["faculty_id"])

    op.create_table(
        "courses",
        _id(), _uuid("institution_id"), _uuid("faculty_id"), _uuid("department_id", nullable=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("credit_units", sa.SmallInteger(), nullable=True),
        _bool("is_active", True), _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.ForeignKeyConstraint(["faculty_id", "institution_id"], ["faculties.id", "faculties.institution_id"], name="fk_courses_faculty_institution", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["department_id", "faculty_id"], ["departments.id", "departments.faculty_id"], name="fk_courses_department_faculty", ondelete="RESTRICT"),
        sa.UniqueConstraint("institution_id", "code", name="uq_courses_institution_id_code"),
        sa.UniqueConstraint("id", "institution_id", name="uq_courses_id_institution_id"),
        sa.CheckConstraint("code = upper(code)", name=op.f("ck_courses_code_uppercase")),
        sa.CheckConstraint("credit_units IS NULL OR credit_units BETWEEN 0 AND 30", name=op.f("ck_courses_credit_units_range")),
    )  # fmt: skip
    op.create_index("ix_courses_faculty_id", "courses", ["faculty_id"])
    op.create_index("ix_courses_department_id", "courses", ["department_id"])

    op.create_table(
        "program_courses",
        _uuid("program_id"), _uuid("course_id"), _uuid("institution_id"),
        sa.Column("year_of_study", sa.SmallInteger(), nullable=True),
        sa.Column("semester", sa.SmallInteger(), nullable=True),
        sa.PrimaryKeyConstraint("program_id", "course_id", name=op.f("pk_program_courses")),
        sa.ForeignKeyConstraint(["program_id", "institution_id"], ["programs.id", "programs.institution_id"], name="fk_program_courses_program_institution", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id", "institution_id"], ["courses.id", "courses.institution_id"], name="fk_program_courses_course_institution", ondelete="CASCADE"),
        sa.CheckConstraint("year_of_study IS NULL OR year_of_study BETWEEN 1 AND 8", name=op.f("ck_program_courses_year_of_study_range")),
        sa.CheckConstraint("semester IS NULL OR semester BETWEEN 1 AND 3", name=op.f("ck_program_courses_semester_range")),
    )  # fmt: skip
    op.create_index("ix_program_courses_course_id", "program_courses", ["course_id"])

    op.create_foreign_key(
        op.f("fk_student_profiles_program_id_programs"), "student_profiles", "programs",
        ["program_id"], ["id"], ondelete="SET NULL",
    )  # fmt: skip

    # ------------------------------------------------------------------ categories, tags, files
    op.create_table(
        "resource_categories",
        _id(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        _bool("is_active", True), _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_categories")),
        sa.UniqueConstraint("name", name=op.f("uq_resource_categories_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_resource_categories_slug")),
    )  # fmt: skip

    op.create_table(
        "tags",
        _id(), sa.Column("name", sa.String(40), nullable=False), _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
        sa.CheckConstraint("name = lower(name)", name=op.f("ck_tags_name_lowercase")),
    )  # fmt: skip

    op.create_table(
        "stored_files",
        _id(),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        _uuid("owner_id"),
        sa.Column("visibility", sa.String(10), server_default="PRIVATE", nullable=False),
        sa.Column("scan_status", sa.String(15), server_default="PENDING", nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_files")),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_stored_files_owner_id_users"), ondelete="RESTRICT"),
        sa.UniqueConstraint("storage_key", name=op.f("uq_stored_files_storage_key")),
        sa.CheckConstraint("visibility IN ('PRIVATE', 'PUBLIC')", name=op.f("ck_stored_files_visibility_valid")),
        sa.CheckConstraint("scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'NOT_SCANNED')", name=op.f("ck_stored_files_scan_status_valid")),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_stored_files_size_positive")),
    )  # fmt: skip
    op.create_index("ix_stored_files_owner_id", "stored_files", ["owner_id"])
    op.create_index("ix_stored_files_sha256", "stored_files", ["sha256"])

    # ------------------------------------------------------------------ resources
    op.create_table(
        "resources",
        _id(), _uuid("institution_id"), _uuid("provider_id"), _uuid("category_id"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("preview_text", sa.String(1000), nullable=True),
        sa.Column("access_type", sa.String(10), server_default="FREE", nullable=False),
        sa.Column("price_ugx", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(20), server_default="DRAFT", nullable=False),
        sa.Column("academic_year", sa.SmallInteger(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), sa.Computed(SEARCH_VECTOR_SQL, persisted=True), nullable=True),
        _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resources")),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], name=op.f("fk_resources_institution_id_institutions"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["provider_id"], ["users.id"], name=op.f("fk_resources_provider_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["resource_categories.id"], name=op.f("fk_resources_category_id_resource_categories"), ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "institution_id", name="uq_resources_id_institution_id"),
        sa.CheckConstraint("status IN ('DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'PUBLISHED', 'ARCHIVED')", name=op.f("ck_resources_status_valid")),
        sa.CheckConstraint("access_type IN ('FREE', 'PREMIUM')", name=op.f("ck_resources_access_type_valid")),
        sa.CheckConstraint(
            "(access_type = 'FREE' AND price_ugx IS NULL) OR "
            "(access_type = 'PREMIUM' AND price_ugx IS NOT NULL AND price_ugx > 0)",
            name=op.f("ck_resources_price_matches_access"),
        ),
        sa.CheckConstraint("academic_year IS NULL OR academic_year BETWEEN 1990 AND 2100", name=op.f("ck_resources_academic_year_range")),
    )  # fmt: skip
    op.create_index("ix_resources_institution_id_status", "resources", ["institution_id", "status"])
    op.create_index("ix_resources_provider_id", "resources", ["provider_id"])
    op.create_index("ix_resources_category_id", "resources", ["category_id"])
    op.create_index("ix_resources_status_published_at", "resources", ["status", "published_at"])
    op.create_index(
        "ix_resources_search_vector", "resources", ["search_vector"], postgresql_using="gin"
    )

    op.create_table(
        "resource_versions",
        _id(), _uuid("resource_id"),
        sa.Column("version_number", sa.Integer(), nullable=False),
        _uuid("file_id"),
        sa.Column("changelog", sa.String(500), nullable=True),
        _bool("is_current", False), _uuid("created_by_user_id"), _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_versions")),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], name=op.f("fk_resource_versions_resource_id_resources"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["stored_files.id"], name=op.f("fk_resource_versions_file_id_stored_files"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_resource_versions_created_by_user_id_users"), ondelete="RESTRICT"),
        sa.UniqueConstraint("file_id", name=op.f("uq_resource_versions_file_id")),
        sa.UniqueConstraint("resource_id", "version_number", name="uq_resource_versions_resource_id_version_number"),
        sa.CheckConstraint("version_number >= 1", name=op.f("ck_resource_versions_version_number_positive")),
    )  # fmt: skip
    op.create_index(
        "uq_resource_versions_current", "resource_versions", ["resource_id"], unique=True,
        postgresql_where=sa.text("is_current"),
    )  # fmt: skip

    op.create_table(
        "resource_tags",
        _uuid("resource_id"), _uuid("tag_id"),
        sa.PrimaryKeyConstraint("resource_id", "tag_id", name=op.f("pk_resource_tags")),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], name=op.f("fk_resource_tags_resource_id_resources"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], name=op.f("fk_resource_tags_tag_id_tags"), ondelete="CASCADE"),
    )  # fmt: skip
    op.create_index("ix_resource_tags_tag_id", "resource_tags", ["tag_id"])

    op.create_table(
        "course_resources",
        _uuid("resource_id"), _uuid("course_id"), _uuid("institution_id"),
        sa.PrimaryKeyConstraint("resource_id", "course_id", name=op.f("pk_course_resources")),
        sa.ForeignKeyConstraint(["resource_id", "institution_id"], ["resources.id", "resources.institution_id"], name="fk_course_resources_resource_institution", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id", "institution_id"], ["courses.id", "courses.institution_id"], name="fk_course_resources_course_institution", ondelete="CASCADE"),
    )  # fmt: skip
    op.create_index("ix_course_resources_course_id", "course_resources", ["course_id"])

    op.create_table(
        "resource_reviews",
        _id(), _uuid("resource_id"), _uuid("version_id", nullable=True), _uuid("actor_user_id"),
        sa.Column("decision", sa.String(15), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
        _ts_clock("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_reviews")),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], name=op.f("fk_resource_reviews_resource_id_resources"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["resource_versions.id"], name=op.f("fk_resource_reviews_version_id_resource_versions"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_resource_reviews_actor_user_id_users"), ondelete="RESTRICT"),
        sa.CheckConstraint("decision IN ('SUBMITTED', 'STARTED', 'APPROVED', 'REJECTED', 'PUBLISHED', 'ARCHIVED')", name=op.f("ck_resource_reviews_decision_valid")),
        sa.CheckConstraint("decision <> 'REJECTED' OR (reason IS NOT NULL AND length(btrim(reason)) > 0)", name=op.f("ck_resource_reviews_rejection_needs_reason")),
    )  # fmt: skip
    op.create_index("ix_resource_reviews_resource_id", "resource_reviews", ["resource_id"])

    op.create_table(
        "entitlements",
        _id(), _uuid("user_id"), _uuid("resource_id"),
        sa.Column("source", sa.String(15), nullable=False),
        sa.Column("source_reference", sa.String(100), nullable=True),
        sa.Column("status", sa.String(10), server_default="ACTIVE", nullable=False),
        _uuid("granted_by_user_id", nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"), _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entitlements")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_entitlements_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], name=op.f("fk_entitlements_resource_id_resources"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], name=op.f("fk_entitlements_granted_by_user_id_users"), ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "resource_id", name="uq_entitlements_user_id_resource_id"),
        sa.CheckConstraint("source IN ('PURCHASE', 'ADMIN_GRANT', 'PROMO')", name=op.f("ck_entitlements_source_valid")),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name=op.f("ck_entitlements_status_valid")),
    )  # fmt: skip
    op.create_index("ix_entitlements_resource_id", "entitlements", ["resource_id"])

    op.create_table(
        "bookmarks",
        _id(), _uuid("user_id"), _uuid("resource_id"), _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookmarks")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_bookmarks_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], name=op.f("fk_bookmarks_resource_id_resources"), ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "resource_id", name="uq_bookmarks_user_id_resource_id"),
    )  # fmt: skip
    op.create_index("ix_bookmarks_user_id_created_at", "bookmarks", ["user_id", "created_at"])

    op.create_table(
        "resource_downloads",
        _id(), _uuid("resource_id"), _uuid("version_id", nullable=True), _uuid("user_id"),
        sa.Column("delivery", sa.String(12), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_downloads")),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], name=op.f("fk_resource_downloads_resource_id_resources"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["resource_versions.id"], name=op.f("fk_resource_downloads_version_id_resource_versions"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_resource_downloads_user_id_users"), ondelete="RESTRICT"),
        sa.CheckConstraint("delivery IN ('SIGNED_URL', 'STREAM')", name=op.f("ck_resource_downloads_delivery_valid")),
    )  # fmt: skip
    op.create_index(
        "ix_resource_downloads_resource_id_created_at",
        "resource_downloads",
        ["resource_id", "created_at"],
    )
    op.create_index("ix_resource_downloads_user_id", "resource_downloads", ["user_id"])

    _seed_reference_data()


def _seed_reference_data() -> None:
    categories = sa.table(
        "resource_categories", sa.column("id", sa.Uuid()), sa.column("name", sa.String()),
        sa.column("slug", sa.String()), sa.column("description", sa.String()), sa.column("sort_order", sa.Integer()),
    )  # fmt: skip
    op.bulk_insert(
        categories,
        [
            {"id": uuid.uuid4(), "name": n, "slug": s, "description": d, "sort_order": o}
            for n, s, d, o in CATEGORIES
        ],
    )

    permissions = sa.table(
        "permissions", sa.column("id", sa.Uuid()), sa.column("code", sa.String()),
        sa.column("description", sa.String()), sa.column("platform_only", sa.Boolean()),
    )  # fmt: skip
    ids = {code: uuid.uuid4() for code, _, _ in NEW_PERMISSIONS}
    op.bulk_insert(
        permissions,
        [
            {"id": ids[c], "code": c, "description": d, "platform_only": po}
            for c, d, po in NEW_PERMISSIONS
        ],
    )
    # ADMIN holds every permission EXCEPT resource:review_own (separation of duties; no default role has it).
    admin_id = (
        op.get_bind().execute(sa.text("SELECT id FROM roles WHERE name = 'ADMIN'")).scalar_one()
    )
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid()), sa.column("permission_id", sa.Uuid())
    )
    op.bulk_insert(
        role_permissions,
        [{"role_id": admin_id, "permission_id": ids[c]} for c in ids if c != "resource:review_own"],
    )


def downgrade() -> None:
    codes = ", ".join(f"'{c}'" for c, _, _ in NEW_PERMISSIONS)
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes})")  # role_permissions rows cascade
    op.drop_constraint(
        op.f("fk_student_profiles_program_id_programs"), "student_profiles", type_="foreignkey"
    )
    for table in (
        "resource_downloads", "bookmarks", "entitlements", "resource_reviews", "course_resources",
        "resource_tags", "resource_versions", "resources", "stored_files", "tags", "resource_categories",
        "program_courses", "courses", "programs", "departments", "faculties",
    ):  # fmt: skip
        op.drop_table(table)
