from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import utcnow
from backend.db.session import Base


class DocumentFolder(Base):
    __tablename__ = "document_folders"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_document_folder_owner_name"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class DocumentMaterial(Base):
    __tablename__ = "document_materials"
    __table_args__ = (
        UniqueConstraint("owner_id", "content_hash", name="uq_material_owner_hash"),
        Index("ix_material_owner_created", "owner_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    folder_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_folders.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(50))
    media_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    subject_type: Mapped[str | None] = mapped_column(String(20))
    subject_id: Mapped[UUID | None]
    ocr_confidence: Mapped[float | None]
    status: Mapped[str] = mapped_column(String(20), default="processed")
    error_message: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class DocumentReviewItem(Base):
    __tablename__ = "document_review_items"
    __table_args__ = (Index("ix_review_owner_status", "owner_id", "status", "id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    material_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_materials.id", ondelete="CASCADE")
    )
    target_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(100))
    evidence: Mapped[str] = mapped_column(String(500))
    confidence: Mapped[float]
    proposed_date: Mapped[str | None] = mapped_column(String(10))
    change_kind: Mapped[str] = mapped_column(String(20), default="new")
    previous_value: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    target_id: Mapped[UUID | None]
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
