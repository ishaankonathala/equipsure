import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, uuid_pk


class PolicyClause(Base):
    __tablename__ = "policy_clauses"
    __table_args__ = (
        CheckConstraint(
            "length(trim(clause_id)) > 0",
            name="ck_policy_clauses_clause_id_nonblank",
        ),
        CheckConstraint(
            "category IN ('COVERAGE', 'EXCLUSION', 'REPORTING', 'LIMIT')",
            name="ck_policy_clauses_category",
        ),
        CheckConstraint(
            "length(trim(summary)) > 0",
            name="ck_policy_clauses_summary_nonblank",
        ),
        CheckConstraint(
            "length(trim(source_reference)) > 0",
            name="ck_policy_clauses_source_nonblank",
        ),
        CheckConstraint(
            "is_fictional = true",
            name="ck_policy_clauses_fictional_true",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    clause_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    is_fictional: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = created_at_column()