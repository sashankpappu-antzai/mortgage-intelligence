import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin, TimestampMixin
from ...shared.types import ConditionSource, ConditionStatus, ConditionType


class Condition(Base, TenantMixin, TimestampMixin):
    __tablename__ = "conditions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False, index=True)

    # Encompass reference
    encompass_condition_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Condition details
    condition_type: Mapped[ConditionType] = mapped_column(nullable=False)
    source: Mapped[ConditionSource] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[ConditionStatus] = mapped_column(default=ConditionStatus.OPEN, index=True)

    # Required document type(s) to satisfy this condition
    required_document_types: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    # Linked documents that satisfy this condition
    linked_document_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)

    # Agent that cleared this condition
    cleared_by_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Metadata
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    loan = relationship("Loan", back_populates="conditions")

    __table_args__ = (
        Index("ix_conditions_loan_status", "loan_id", "status"),
    )
