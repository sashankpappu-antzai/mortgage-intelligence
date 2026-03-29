import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from ..dependencies import DB, CurrentUser
from ..db.models.condition import Condition
from ..db.models.document import Document
from ..db.models.loan import Loan, LoanBorrower
from ..services.rules.doc_requirements.checklists import generate_checklist
from ..shared.types import (
    BorrowerPersona,
    ConditionStatus,
    DocumentStatus,
    LoanStatus,
    ProcessingPhase,
    UserRole,
)

router = APIRouter(prefix="/loans", tags=["loans"])


# --- Schemas ---


class BorrowerCreate(BaseModel):
    first_name: str
    last_name: str
    middle_name: str | None = None
    email: str | None = None
    phone: str | None = None
    borrower_type: str = "primary"
    employment_type: str | None = None
    self_employed: bool | None = None
    ownership_percentage: float | None = None
    income_sources: dict | None = None


class LoanCreate(BaseModel):
    loan_purpose: str = "purchase"
    occupancy_type: str = "primary"
    property_type: str | None = None
    loan_amount: float | None = None
    purchase_price: float | None = None
    interest_rate: float | None = None
    loan_term_months: int = 360
    encompass_loan_id: str | None = None
    encompass_loan_number: str | None = None
    borrowers: list[BorrowerCreate] = []


class LoanSummary(BaseModel):
    id: str
    encompass_loan_number: str | None
    status: str
    processing_phase: str
    primary_borrower_persona: str | None
    borrower_name: str | None
    loan_amount: float | None
    loan_purpose: str | None
    ai_readiness_score: float | None
    created_at: datetime
    updated_at: datetime


class LoanDetail(LoanSummary):
    encompass_loan_id: str | None
    occupancy_type: str | None
    property_type: str | None
    purchase_price: float | None
    appraised_value: float | None
    interest_rate: float | None
    loan_term_months: int | None
    ltv: float | None
    cltv: float | None
    dti_front: float | None
    dti_back: float | None
    qualifying_income_monthly: float | None
    aus_type: str | None
    aus_finding: str | None
    credit_score_borrower: int | None
    representative_credit_score: int | None
    encompass_milestone: str | None
    borrowers: list[dict]
    document_checklist: list[dict]
    conditions_summary: dict


class ChecklistItem(BaseModel):
    document_type: str
    category: str
    label: str
    required: bool
    status: str  # missing, uploaded, validated, rejected
    description: str | None = None


# --- Endpoints ---


@router.get("", response_model=list[LoanSummary])
async def list_loans(
    user: CurrentUser,
    db: DB,
    status_filter: LoanStatus | None = Query(None, alias="status"),
    phase: ProcessingPhase | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = select(Loan).where(Loan.tenant_id == user.tenant_id)

    # LOs see only their loans, UWs and admins see all
    if user.role == UserRole.LOAN_OFFICER:
        query = query.where(Loan.loan_officer_id == user.id)

    if status_filter:
        query = query.where(Loan.status == status_filter)
    if phase:
        query = query.where(Loan.processing_phase == phase)

    query = query.order_by(Loan.updated_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    loans = result.scalars().all()

    summaries = []
    for loan in loans:
        borrower_name = None
        if loan.borrowers:
            primary = next((b for b in loan.borrowers if b.borrower_type == "primary"), loan.borrowers[0])
            borrower_name = f"{primary.first_name} {primary.last_name}"

        summaries.append(
            LoanSummary(
                id=str(loan.id),
                encompass_loan_number=loan.encompass_loan_number,
                status=loan.status,
                processing_phase=loan.processing_phase,
                primary_borrower_persona=loan.primary_borrower_persona,
                borrower_name=borrower_name,
                loan_amount=float(loan.loan_amount) if loan.loan_amount else None,
                loan_purpose=loan.loan_purpose,
                ai_readiness_score=float(loan.ai_readiness_score) if loan.ai_readiness_score else None,
                created_at=loan.created_at,
                updated_at=loan.updated_at,
            )
        )
    return summaries


@router.post("", response_model=LoanDetail, status_code=status.HTTP_201_CREATED)
async def create_loan(req: LoanCreate, user: CurrentUser, db: DB):
    from ..services.rules.doc_requirements.checklists import classify_persona

    loan = Loan(
        tenant_id=user.tenant_id,
        loan_officer_id=user.id,
        loan_purpose=req.loan_purpose,
        occupancy_type=req.occupancy_type,
        property_type=req.property_type,
        loan_amount=req.loan_amount,
        purchase_price=req.purchase_price,
        interest_rate=req.interest_rate,
        loan_term_months=req.loan_term_months,
        encompass_loan_id=req.encompass_loan_id,
        encompass_loan_number=req.encompass_loan_number,
        status=LoanStatus.INTAKE,
        processing_phase=ProcessingPhase.INTAKE,
    )
    db.add(loan)
    await db.flush()

    borrowers = []
    for b in req.borrowers:
        borrower = LoanBorrower(
            loan_id=loan.id,
            tenant_id=user.tenant_id,
            first_name=b.first_name,
            last_name=b.last_name,
            middle_name=b.middle_name,
            email=b.email,
            phone=b.phone,
            borrower_type=b.borrower_type,
            employment_type=b.employment_type,
            self_employed=b.self_employed,
            ownership_percentage=b.ownership_percentage,
            income_sources=b.income_sources,
        )
        # Classify persona
        borrower.persona = classify_persona(
            employment_type=b.employment_type,
            self_employed=b.self_employed,
            ownership_percentage=b.ownership_percentage,
            income_sources=b.income_sources,
        )
        db.add(borrower)
        borrowers.append(borrower)

    # Set primary borrower persona on loan
    primary = next((b for b in borrowers if b.borrower_type == "primary"), borrowers[0] if borrowers else None)
    if primary:
        loan.primary_borrower_persona = primary.persona

    await db.flush()

    # Generate checklist
    checklist = _build_checklist(loan, borrowers, [])

    return _loan_to_detail(loan, borrowers, checklist, {"open": 0, "received": 0, "cleared": 0, "total": 0})


@router.get("/{loan_id}", response_model=LoanDetail)
async def get_loan(loan_id: uuid.UUID, user: CurrentUser, db: DB):
    loan = await _get_loan_or_404(loan_id, user, db)

    # Get conditions summary
    cond_result = await db.execute(select(Condition).where(Condition.loan_id == loan.id))
    conditions = cond_result.scalars().all()
    cond_summary = {
        "open": sum(1 for c in conditions if c.status == ConditionStatus.OPEN),
        "requested": sum(1 for c in conditions if c.status == ConditionStatus.REQUESTED),
        "received": sum(1 for c in conditions if c.status == ConditionStatus.RECEIVED),
        "cleared": sum(1 for c in conditions if c.status == ConditionStatus.CLEARED),
        "total": len(conditions),
    }

    # Get documents for checklist status
    doc_result = await db.execute(select(Document).where(Document.loan_id == loan.id))
    documents = doc_result.scalars().all()

    checklist = _build_checklist(loan, loan.borrowers, documents)

    return _loan_to_detail(loan, loan.borrowers, checklist, cond_summary)


async def _get_loan_or_404(loan_id: uuid.UUID, user: CurrentUser, db: DB) -> Loan:
    result = await db.execute(select(Loan).where(Loan.id == loan_id, Loan.tenant_id == user.tenant_id))
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return loan


def _build_checklist(loan: Loan, borrowers: list, documents: list) -> list[dict]:
    """Build document checklist based on persona and check against uploaded docs."""
    personas = [b.persona for b in borrowers if b.persona] if borrowers else []
    primary_persona = loan.primary_borrower_persona

    if not primary_persona and personas:
        primary_persona = personas[0]

    required_docs = generate_checklist(
        persona=primary_persona,
        loan_purpose=loan.loan_purpose,
        occupancy_type=loan.occupancy_type,
        property_type=loan.property_type,
        has_coborrower=len(borrowers) > 1 if borrowers else False,
    )

    # Map uploaded docs
    uploaded_types = {}
    for doc in documents:
        if doc.document_type:
            if doc.status in (DocumentStatus.VALIDATED, DocumentStatus.EXTRACTED):
                uploaded_types[doc.document_type] = "validated"
            elif doc.status == DocumentStatus.REJECTED:
                uploaded_types.setdefault(doc.document_type, "rejected")
            else:
                uploaded_types.setdefault(doc.document_type, "uploaded")

    checklist = []
    for item in required_docs:
        doc_status = uploaded_types.get(item["document_type"], "missing")
        checklist.append({**item, "status": doc_status})
    return checklist


def _loan_to_detail(loan, borrowers, checklist, cond_summary) -> LoanDetail:
    borrower_name = None
    borrower_dicts = []
    for b in borrowers:
        if b.borrower_type == "primary" or borrower_name is None:
            borrower_name = f"{b.first_name} {b.last_name}"
        borrower_dicts.append({
            "id": str(b.id),
            "first_name": b.first_name,
            "last_name": b.last_name,
            "borrower_type": b.borrower_type,
            "persona": b.persona,
            "employment_type": b.employment_type,
            "self_employed": b.self_employed,
        })

    return LoanDetail(
        id=str(loan.id),
        encompass_loan_id=loan.encompass_loan_id,
        encompass_loan_number=loan.encompass_loan_number,
        status=loan.status,
        processing_phase=loan.processing_phase,
        primary_borrower_persona=loan.primary_borrower_persona,
        borrower_name=borrower_name,
        loan_amount=float(loan.loan_amount) if loan.loan_amount else None,
        loan_purpose=loan.loan_purpose,
        occupancy_type=loan.occupancy_type,
        property_type=loan.property_type,
        purchase_price=float(loan.purchase_price) if loan.purchase_price else None,
        appraised_value=float(loan.appraised_value) if loan.appraised_value else None,
        interest_rate=float(loan.interest_rate) if loan.interest_rate else None,
        loan_term_months=loan.loan_term_months,
        ltv=float(loan.ltv) if loan.ltv else None,
        cltv=float(loan.cltv) if loan.cltv else None,
        dti_front=float(loan.dti_front) if loan.dti_front else None,
        dti_back=float(loan.dti_back) if loan.dti_back else None,
        qualifying_income_monthly=float(loan.qualifying_income_monthly) if loan.qualifying_income_monthly else None,
        aus_type=loan.aus_type,
        aus_finding=loan.aus_finding,
        credit_score_borrower=loan.credit_score_borrower,
        representative_credit_score=loan.representative_credit_score,
        encompass_milestone=loan.encompass_milestone,
        ai_readiness_score=float(loan.ai_readiness_score) if loan.ai_readiness_score else None,
        created_at=loan.created_at,
        updated_at=loan.updated_at,
        borrowers=borrower_dicts,
        document_checklist=checklist,
        conditions_summary=cond_summary,
    )
