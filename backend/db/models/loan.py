import uuid

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin, TimestampMixin
from ...shared.types import BorrowerPersona, LoanStatus, ProcessingPhase


class Loan(Base, TenantMixin, TimestampMixin):
    __tablename__ = "loans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encompass_loan_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    encompass_loan_number: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Loan officer
    loan_officer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Classification
    primary_borrower_persona: Mapped[BorrowerPersona | None] = mapped_column(nullable=True)

    # Status tracking
    status: Mapped[LoanStatus] = mapped_column(default=LoanStatus.CREATED, index=True)
    processing_phase: Mapped[ProcessingPhase] = mapped_column(default=ProcessingPhase.INTAKE)
    encompass_milestone: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Loan details (cached from Encompass)
    loan_purpose: Mapped[str | None] = mapped_column(String(50), nullable=True)  # purchase, refinance, cashout_refi
    occupancy_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # primary, secondary, investment
    property_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    loan_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    purchase_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    appraised_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    interest_rate: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    loan_term_months: Mapped[int | None] = mapped_column(nullable=True)

    # Ratios (calculated by agents)
    ltv: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    cltv: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    dti_front: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    dti_back: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    qualifying_income_monthly: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    # AUS
    aus_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # DU or LP
    aus_finding: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Approve/Eligible, Refer/Caution
    aus_case_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Credit
    credit_score_borrower: Mapped[int | None] = mapped_column(nullable=True)
    credit_score_coborrower: Mapped[int | None] = mapped_column(nullable=True)
    representative_credit_score: Mapped[int | None] = mapped_column(nullable=True)

    # AI readiness
    ai_readiness_score: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="0-100 score indicating how ready the file is for UW"
    )

    # Full loan data snapshot from Encompass
    loan_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    loan_officer = relationship("User", foreign_keys=[loan_officer_id], lazy="selectin")
    borrowers = relationship("LoanBorrower", back_populates="loan", lazy="selectin")
    documents = relationship("Document", back_populates="loan", lazy="noload")
    conditions = relationship("Condition", back_populates="loan", lazy="noload")
    validations = relationship("AgentValidation", back_populates="loan", lazy="noload")
    tenant = relationship("Tenant", back_populates="loans", lazy="selectin")

    __table_args__ = (
        Index("ix_loans_status_phase", "status", "processing_phase"),
        Index("ix_loans_lo_status", "loan_officer_id", "status"),
    )


class LoanBorrower(Base, TenantMixin, TimestampMixin):
    __tablename__ = "loan_borrowers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("loans.id"), nullable=False, index=True)

    borrower_type: Mapped[str] = mapped_column(String(20), nullable=False)  # primary, coborrower
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ssn_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="Salted hash, never raw SSN")

    persona: Mapped[BorrowerPersona | None] = mapped_column(nullable=True)
    encompass_borrower_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Employment (cached from 1003)
    employment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    years_in_profession: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    self_employed: Mapped[bool | None] = mapped_column(nullable=True)
    ownership_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Income sources (from 1003)
    income_sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    loan = relationship("Loan", back_populates="borrowers")
