import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk


class AIAssessment(Base):
    __tablename__ = "ai_assessments"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('fake', 'gemini')",
            name="ck_ai_assessments_provider",
        ),
        CheckConstraint(
            "length(trim(prompt_version)) > 0",
            name="ck_ai_assessments_prompt_version_nonblank",
        ),
        CheckConstraint(
            "validation_status IN ('VALID', 'INVALID')",
            name="ck_ai_assessments_validation_status",
        ),
        CheckConstraint(
            "advisory_only = true",
            name="ck_ai_assessments_advisory_true",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    advisory_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cited_clause_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()