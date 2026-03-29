"""
UW Dashboard endpoints.
Provides the single-view dashboard data for underwriters.
"""

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from ..dependencies import DB, CurrentUser
from ..events.sse import subscribe_loan, subscribe_pipeline
from ..db.models.agent_validation import AgentValidation
from ..db.models.condition import Condition
from ..db.models.document import Document
from ..db.models.loan import Loan
from ..shared.types import ConditionStatus, LoanStatus, ProcessingPhase, UserRole

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class PipelineItem(BaseModel):
    loan_id: str
    encompass_loan_number: str | None
    borrower_name: str | None
    loan_officer_name: str | None
    loan_amount: float | None
    status: str
    processing_phase: str
    ai_readiness_score: float | None
    primary_borrower_persona: str | None
    conditions_open: int
    conditions_total: int
    documents_uploaded: int
    documents_validated: int
    credit_score: int | None
    dti_back: float | None
    ltv: float | None
    updated_at: str


class ValidationItem(BaseModel):
    id: str
    agent_name: str
    validation_type: str
    confidence_score: float
    confidence_level: str
    status: str
    flags: dict | None
    created_at: str


class LoanReviewData(BaseModel):
    loan: dict
    borrowers: list[dict]
    validations: list[ValidationItem]
    conditions: list[dict]
    documents_summary: dict
    risk_flags: list[dict]


@router.get("/pipeline", response_model=list[PipelineItem])
async def get_pipeline(
    user: CurrentUser,
    db: DB,
    status_filter: LoanStatus | None = Query(None, alias="status"),
    limit: int = Query(50, le=200),
):
    """Get UW pipeline view - all loans with their AI readiness scores."""
    query = select(Loan).where(Loan.tenant_id == user.tenant_id)

    if status_filter:
        query = query.where(Loan.status == status_filter)
    else:
        # Default: show loans that are in processing or later
        query = query.where(Loan.status.not_in([LoanStatus.FUNDED, LoanStatus.DENIED]))

    query = query.order_by(Loan.updated_at.desc()).limit(limit)
    result = await db.execute(query)
    loans = result.scalars().all()

    items = []
    for loan in loans:
        # Get condition counts
        cond_result = await db.execute(
            select(
                func.count(Condition.id).label("total"),
                func.count(Condition.id).filter(Condition.status == ConditionStatus.OPEN).label("open"),
            ).where(Condition.loan_id == loan.id)
        )
        cond_row = cond_result.one()

        # Get document counts
        doc_result = await db.execute(
            select(
                func.count(Document.id).label("total"),
                func.count(Document.id).filter(Document.status == "validated").label("validated"),
            ).where(Document.loan_id == loan.id)
        )
        doc_row = doc_result.one()

        borrower_name = None
        if loan.borrowers:
            primary = next((b for b in loan.borrowers if b.borrower_type == "primary"), loan.borrowers[0])
            borrower_name = f"{primary.first_name} {primary.last_name}"

        lo_name = loan.loan_officer.name if loan.loan_officer else None

        items.append(PipelineItem(
            loan_id=str(loan.id),
            encompass_loan_number=loan.encompass_loan_number,
            borrower_name=borrower_name,
            loan_officer_name=lo_name,
            loan_amount=float(loan.loan_amount) if loan.loan_amount else None,
            status=loan.status,
            processing_phase=loan.processing_phase,
            ai_readiness_score=float(loan.ai_readiness_score) if loan.ai_readiness_score else None,
            primary_borrower_persona=loan.primary_borrower_persona,
            conditions_open=cond_row.open,
            conditions_total=cond_row.total,
            documents_uploaded=doc_row.total,
            documents_validated=doc_row.validated,
            credit_score=loan.representative_credit_score,
            dti_back=float(loan.dti_back) if loan.dti_back else None,
            ltv=float(loan.ltv) if loan.ltv else None,
            updated_at=loan.updated_at.isoformat(),
        ))

    return items


@router.get("/loan/{loan_id}/review", response_model=LoanReviewData)
async def get_loan_review(loan_id: uuid.UUID, user: CurrentUser, db: DB):
    """Get complete loan review data for UW single-view dashboard."""
    result = await db.execute(
        select(Loan).where(Loan.id == loan_id, Loan.tenant_id == user.tenant_id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get all validations
    val_result = await db.execute(
        select(AgentValidation)
        .where(AgentValidation.loan_id == loan_id)
        .order_by(AgentValidation.created_at.desc())
    )
    validations = val_result.scalars().all()

    # Get all conditions
    cond_result = await db.execute(
        select(Condition).where(Condition.loan_id == loan_id).order_by(Condition.created_at)
    )
    conditions = cond_result.scalars().all()

    # Get document summary
    doc_result = await db.execute(select(Document).where(Document.loan_id == loan_id))
    documents = doc_result.scalars().all()
    doc_summary = {
        "total": len(documents),
        "by_status": {},
        "by_category": {},
    }
    for doc in documents:
        doc_summary["by_status"][doc.status] = doc_summary["by_status"].get(doc.status, 0) + 1
        if doc.category:
            doc_summary["by_category"][doc.category] = doc_summary["by_category"].get(doc.category, 0) + 1

    # Aggregate risk flags from all validations
    risk_flags = []
    for v in validations:
        if v.flags:
            for flag_key, flag_data in v.flags.items():
                risk_flags.append({
                    "source_agent": v.agent_name,
                    "flag_type": flag_key,
                    "severity": flag_data.get("severity", "info"),
                    "message": flag_data.get("message", ""),
                    "details": flag_data,
                })

    return LoanReviewData(
        loan={
            "id": str(loan.id),
            "encompass_loan_number": loan.encompass_loan_number,
            "status": loan.status,
            "processing_phase": loan.processing_phase,
            "persona": loan.primary_borrower_persona,
            "loan_amount": float(loan.loan_amount) if loan.loan_amount else None,
            "loan_purpose": loan.loan_purpose,
            "ltv": float(loan.ltv) if loan.ltv else None,
            "dti_front": float(loan.dti_front) if loan.dti_front else None,
            "dti_back": float(loan.dti_back) if loan.dti_back else None,
            "qualifying_income": float(loan.qualifying_income_monthly) if loan.qualifying_income_monthly else None,
            "credit_score": loan.representative_credit_score,
            "aus_type": loan.aus_type,
            "aus_finding": loan.aus_finding,
            "ai_readiness_score": float(loan.ai_readiness_score) if loan.ai_readiness_score else None,
        },
        borrowers=[
            {
                "id": str(b.id),
                "name": f"{b.first_name} {b.last_name}",
                "type": b.borrower_type,
                "persona": b.persona,
                "employment_type": b.employment_type,
            }
            for b in loan.borrowers
        ],
        validations=[
            ValidationItem(
                id=str(v.id),
                agent_name=v.agent_name,
                validation_type=v.validation_type,
                confidence_score=float(v.confidence_score),
                confidence_level=v.confidence_level,
                status=v.status,
                flags=v.flags,
                created_at=v.created_at.isoformat(),
            )
            for v in validations
        ],
        conditions=[
            {
                "id": str(c.id),
                "type": c.condition_type,
                "source": c.source,
                "title": c.title,
                "status": c.status,
                "cleared_by_agent": c.cleared_by_agent,
            }
            for c in conditions
        ],
        documents_summary=doc_summary,
        risk_flags=risk_flags,
    )


# --- SSE Endpoints ---


@router.get("/events/pipeline")
async def pipeline_events(user: CurrentUser):
    """SSE stream for real-time pipeline updates (UW dashboard)."""
    return StreamingResponse(
        subscribe_pipeline(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/events/loan/{loan_id}")
async def loan_events(loan_id: str, user: CurrentUser):
    """SSE stream for real-time loan-specific updates."""
    return StreamingResponse(
        subscribe_loan(loan_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
