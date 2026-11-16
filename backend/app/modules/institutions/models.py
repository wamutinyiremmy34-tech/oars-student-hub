import sqlalchemy as sa
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Institution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A university/college. The academic hierarchy (faculties, programs, ...) arrives in the next phase."""

    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    country_code: Mapped[str] = mapped_column(String(2), server_default="UG")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sa.true())
