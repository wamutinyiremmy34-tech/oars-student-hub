import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StoredFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata for one blob in object storage. The storage key is internal and never serialised."""

    __tablename__ = "stored_files"
    __table_args__ = (
        CheckConstraint("visibility IN ('PRIVATE', 'PUBLIC')", name="visibility_valid"),
        CheckConstraint(
            "scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'NOT_SCANNED')",
            name="scan_status_valid",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        Index("ix_stored_files_owner_id", "owner_id"),
        Index("ix_stored_files_sha256", "sha256"),
    )

    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))  # sanitised display name only
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    visibility: Mapped[str] = mapped_column(String(10), server_default="PRIVATE")
    scan_status: Mapped[str] = mapped_column(String(15), server_default="PENDING")
