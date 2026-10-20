import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk
from app.models.enums import DocumentType


class ClaimDocument(Base):
    __tablename__ = "claim_documents"
    __table_args__ = (
        CheckConstraint(
            f"document_type IN ({', '.join(repr(s.value) for s in DocumentType)})",
            name="ck_claim_documents_type",
        ),
        CheckConstraint(
            "length(storage_name) > 0",
            name="ck_claim_documents_storage_name_nonempty",
        ),
        CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="ck_claim_documents_content_type",
        ),
        CheckConstraint(
            "size_bytes > 0",
            name="ck_claim_documents_size_positive",
        ),
        CheckConstraint(
            "size_bytes <= 10485760",
            name="ck_claim_documents_size_limit",
        ),
        CheckConstraint(
            "length(sha256) = 64",
            name="ck_claim_documents_sha256_length",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(30), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = created_at_column()
