import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Preview = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
# The pattern allows upper case because lower-casing is applied by the same constraint set.
TagName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}[A-Za-z0-9]$"
    ),
]
AccessLiteral = Literal["FREE", "PREMIUM"]


class ResourceCreate(BaseModel):
    institution_id: uuid.UUID
    category_id: uuid.UUID
    title: Title
    description: Description = ""
    preview_text: Preview | None = None
    access_type: AccessLiteral = "FREE"
    price_ugx: int | None = Field(
        default=None, gt=0, le=100_000_000, description="Integer UGX, no decimals"
    )
    academic_year: int | None = Field(default=None, ge=1990, le=2100)
    tags: list[TagName] = Field(default_factory=list, max_length=10)
    course_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _price_matches_access(self) -> Self:
        if self.access_type == "PREMIUM" and self.price_ugx is None:
            raise ValueError("price_ugx is required for PREMIUM resources")
        if self.access_type == "FREE" and self.price_ugx is not None:
            raise ValueError("price_ugx must be empty for FREE resources")
        return self


class ResourcePatch(BaseModel):
    category_id: uuid.UUID | None = None
    title: Title | None = None
    description: Description | None = None
    preview_text: Preview | None = None
    access_type: AccessLiteral | None = None
    price_ugx: int | None = Field(default=None, gt=0, le=100_000_000)
    academic_year: int | None = Field(default=None, ge=1990, le=2100)
    tags: list[TagName] | None = Field(default=None, max_length=10)
    course_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


class RejectIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]


class NoteIn(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class GrantEntitlementIn(BaseModel):
    user_id: uuid.UUID
    expires_at: datetime | None = None
    source_reference: Annotated[str, StringConstraints(max_length=100)] | None = None


class CategoryIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    description: Annotated[str, StringConstraints(max_length=255)] | None = None
    sort_order: int = Field(default=0, ge=0, le=1000)


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None


class CourseRef(BaseModel):
    id: uuid.UUID
    code: str
    title: str


class VersionOut(BaseModel):
    """File details a client may see. There is deliberately no storage key or file id here."""

    id: uuid.UUID
    version_number: int
    filename: str
    mime_type: str
    size_bytes: int
    is_current: bool
    changelog: str | None
    created_at: datetime


class ReviewOut(BaseModel):
    decision: str
    reason: str | None
    created_at: datetime


class ViewerOut(BaseModel):
    """What the signed-in (or anonymous) caller may do. The API re-checks on every action."""

    is_owner: bool
    can_download: bool
    download_block_reason: str | None
    is_bookmarked: bool
    can_review: bool
    can_publish: bool
    entitlement_status: str | None


class ResourceSummary(BaseModel):
    id: uuid.UUID
    title: str
    excerpt: str
    access_type: str
    price_ugx: int | None
    status: str
    institution_id: uuid.UUID
    institution_name: str
    category: CategoryOut
    tags: list[str]
    courses: list[CourseRef]
    academic_year: int | None
    provider_name: str
    published_at: datetime | None
    file: VersionOut | None
    is_bookmarked: bool


class ResourceDetail(ResourceSummary):
    description: str
    preview_text: str | None
    versions: list[VersionOut]
    viewer: ViewerOut
    latest_review: ReviewOut | None


class DownloadOut(BaseModel):
    url: str
    expires_in: int
    filename: str
    delivery: Literal["SIGNED_URL", "STREAM"]


class StatsOut(BaseModel):
    downloads_total: int
    downloads_last_30_days: int
    bookmarks: int
    active_entitlements: int


class EntitlementOut(BaseModel):
    resource_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    source: str
    expires_at: datetime | None


class SearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    institution_id: uuid.UUID | None = None
    faculty_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    program_id: uuid.UUID | None = None
    course_id: uuid.UUID | None = None
    category: Annotated[str, StringConstraints(max_length=80)] | None = None
    tag: Annotated[str, StringConstraints(max_length=40)] | None = None
    access: AccessLiteral | None = None
    academic_year: int | None = Field(default=None, ge=1990, le=2100)
    sort: Literal["relevance", "newest", "title"] | None = None
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=12, ge=1, le=50)
