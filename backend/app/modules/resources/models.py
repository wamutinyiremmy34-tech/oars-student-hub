"""Resources, versions, categories, tags, moderation history, entitlements, bookmarks, download log."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResourceStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"

    ALL = (DRAFT, SUBMITTED, UNDER_REVIEW, APPROVED, REJECTED, PUBLISHED, ARCHIVED)


class AccessType:
    FREE = "FREE"
    PREMIUM = "PREMIUM"


REVIEW_DECISIONS = ("SUBMITTED", "STARTED", "APPROVED", "REJECTED", "PUBLISHED", "ARCHIVED")
ENTITLEMENT_SOURCES = ("PURCHASE", "ADMIN_GRANT", "PROMO")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ResourceCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Admin-managed (a table, not an enum) so new resource types need no code change."""

    __tablename__ = "resource_categories"

    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Tag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (CheckConstraint("name = lower(name)", name="name_lowercase"),)

    name: Mapped[str] = mapped_column(String(40), unique=True)


class Resource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("id", "institution_id", name="uq_resources_id_institution_id"),
        CheckConstraint(_in("status", ResourceStatus.ALL), name="status_valid"),
        CheckConstraint(_in("access_type", ("FREE", "PREMIUM")), name="access_type_valid"),
        # Money is integer UGX. PREMIUM needs a positive price; FREE must not have one.
        CheckConstraint(
            "(access_type = 'FREE' AND price_ugx IS NULL) OR "
            "(access_type = 'PREMIUM' AND price_ugx IS NOT NULL AND price_ugx > 0)",
            name="price_matches_access",
        ),
        CheckConstraint(
            "academic_year IS NULL OR academic_year BETWEEN 1990 AND 2100",
            name="academic_year_range",
        ),
        Index("ix_resources_institution_id_status", "institution_id", "status"),
        Index("ix_resources_provider_id", "provider_id"),
        Index("ix_resources_category_id", "category_id"),
        Index("ix_resources_status_published_at", "status", "published_at"),
        Index("ix_resources_search_vector", "search_vector", postgresql_using="gin"),
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT")
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resource_categories.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, server_default="")
    preview_text: Mapped[str | None] = mapped_column(String(1000))
    access_type: Mapped[str] = mapped_column(String(10), server_default="FREE")
    price_ugx: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), server_default="DRAFT")
    academic_year: Mapped[int | None] = mapped_column(SmallInteger)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Maintained by PostgreSQL itself, so it can never go stale. Full-text search runs on this column.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))",
            persisted=True,
        ),
        nullable=True,
    )


class ResourceVersion(UUIDPrimaryKeyMixin, Base):
    """History is never overwritten. Exactly one version per resource may be marked current."""

    __tablename__ = "resource_versions"
    __table_args__ = (
        UniqueConstraint(
            "resource_id", "version_number", name="uq_resource_versions_resource_id_version_number"
        ),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        Index(
            "uq_resource_versions_current",
            "resource_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer)
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), unique=True
    )
    changelog: Mapped[str | None] = mapped_column(String(500))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResourceTag(Base):
    __tablename__ = "resource_tags"
    __table_args__ = (Index("ix_resource_tags_tag_id", "tag_id"),)

    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class CourseResource(Base):
    """Links a resource to a course. Both composite FKs carry institution_id, so a resource can only
    ever be linked to a course of its own institution (enforced by the database)."""

    __tablename__ = "course_resources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["resource_id", "institution_id"], ["resources.id", "resources.institution_id"],
            name="fk_course_resources_resource_institution", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["course_id", "institution_id"], ["courses.id", "courses.institution_id"],
            name="fk_course_resources_course_institution", ondelete="CASCADE",
        ),
        Index("ix_course_resources_course_id", "course_id"),
    )  # fmt: skip

    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))


class ResourceReview(UUIDPrimaryKeyMixin, Base):
    """Append-only moderation/lifecycle history: who did what, when, and why."""

    __tablename__ = "resource_reviews"
    __table_args__ = (
        CheckConstraint(_in("decision", REVIEW_DECISIONS), name="decision_valid"),
        CheckConstraint(
            "decision <> 'REJECTED' OR (reason IS NOT NULL AND length(btrim(reason)) > 0)",
            name="rejection_needs_reason",
        ),
        Index("ix_resource_reviews_resource_id", "resource_id"),
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"))
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resource_versions.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decision: Mapped[str] = mapped_column(String(15))
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class Entitlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The right of one user to download one premium resource. One row per (user, resource):
    revoking sets status REVOKED and re-granting reactivates the same row."""

    __tablename__ = "entitlements"
    __table_args__ = (
        UniqueConstraint("user_id", "resource_id", name="uq_entitlements_user_id_resource_id"),
        CheckConstraint(_in("source", ENTITLEMENT_SOURCES), name="source_valid"),
        CheckConstraint("status IN ('ACTIVE', 'REVOKED')", name="status_valid"),
        Index("ix_entitlements_resource_id", "resource_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id", ondelete="RESTRICT"))
    source: Mapped[str] = mapped_column(String(15))
    source_reference: Mapped[str | None] = mapped_column(String(100))  # e.g. a payment id, later
    status: Mapped[str] = mapped_column(String(10), server_default="ACTIVE")
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Bookmark(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "resource_id", name="uq_bookmarks_user_id_resource_id"),
        Index("ix_bookmarks_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResourceDownload(UUIDPrimaryKeyMixin, Base):
    """One row per authorised download link issued (the audit trail for access to content)."""

    __tablename__ = "resource_downloads"
    __table_args__ = (
        CheckConstraint("delivery IN ('SIGNED_URL', 'STREAM')", name="delivery_valid"),
        Index("ix_resource_downloads_resource_id_created_at", "resource_id", "created_at"),
        Index("ix_resource_downloads_user_id", "user_id"),
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"))
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resource_versions.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    delivery: Mapped[str] = mapped_column(String(12))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
