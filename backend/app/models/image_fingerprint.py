import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk


class ImageFingerprint(Base):
    __tablename__ = "image_fingerprints"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claim_documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dhash: Mapped[str] = mapped_column(String(16), nullable=False)
    blur_score: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = created_at_column()

