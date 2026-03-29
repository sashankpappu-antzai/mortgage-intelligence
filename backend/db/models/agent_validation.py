import uuid

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin, TimestampMixin
from ...shared.types import ConfidenceLevel


class AgentValidation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "agent_validations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False, index=True)

    # Agent info
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    validation_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Input documents that were analyzed
    input_document_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)

    # Result - the full structured output from the agent
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Confidence
    confidence_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    confidence_level: Mapped[ConfidenceLevel] = mapped_column(nullable=False)

    # Flags for UW attention
    flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # LLM usage tracking
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_tokens_used: Mapped[int | None] = mapped_column(nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")

    loan = relationship("Loan", back_populates="validations")

    __table_args__ = (
        Index("ix_agent_validations_loan_agent", "loan_id", "agent_name"),
    )
