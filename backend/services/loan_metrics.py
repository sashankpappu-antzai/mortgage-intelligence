"""
Loan metrics calculation engine.

Computes LTV, CLTV, DTI, qualifying income, credit scores, and AI readiness
from document extracted_data and loan fields. All financial math is deterministic
Python -- no LLM involvement per project conventions.
"""

import logging
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from ..db.models.agent_validation import AgentValidation
from ..db.models.condition import Condition
from ..db.models.document import Document
from ..db.models.loan import Loan
from ..db.postgres import get_db_session
from ..events.sse import broadcast_loan_event
from ..services.rules.doc_requirements.checklists import generate_checklist
from ..shared.types import ConditionStatus, DocumentStatus, DocumentType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pay frequency annualization factors
# ---------------------------------------------------------------------------
PAY_FREQUENCY_ANNUAL_FACTORS: dict[str, float] = {
    "weekly": 52.0,
    "biweekly": 26.0,
    "semimonthly": 24.0,
    "semi-monthly": 24.0,
    "monthly": 12.0,
    "annually": 1.0,
    "annual": 1.0,
}

# Document statuses that count as "received / processed"
_PROCESSED_STATUSES = frozenset({
    DocumentStatus.CLASSIFIED,
    DocumentStatus.VALIDATED,
    DocumentStatus.EXTRACTED,
})

# Freshness windows in days
_FRESHNESS_WINDOWS: dict[DocumentType, int] = {
    DocumentType.PAY_STUB: 30,
    DocumentType.BANK_STATEMENT: 60,
    DocumentType.CREDIT_REPORT: 120,
    DocumentType.VOE_WRITTEN: 120,
    DocumentType.VOE_VERBAL: 10,
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _safe_float(val: Any) -> float | None:
    """Safely convert a value that may contain $, commas, or whitespace to float.

    Returns None when the value cannot be interpreted as a number.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r"[,$\s]", "", val.strip())
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _safe_int(val: Any) -> int | None:
    """Safely convert to int via _safe_float."""
    f = _safe_float(val)
    if f is None:
        return None
    return int(round(f))


def _get_extracted(doc: Document, field: str) -> Any:
    """Retrieve a field from a document's extracted_data, returning None if missing."""
    if not doc.extracted_data:
        return None
    return doc.extracted_data.get(field)


def _annualization_factor(pay_frequency: str | None) -> float | None:
    """Return the annualization multiplier for a pay frequency string."""
    if not pay_frequency:
        return None
    return PAY_FREQUENCY_ANNUAL_FACTORS.get(pay_frequency.strip().lower())


# ---------------------------------------------------------------------------
# Property value
# ---------------------------------------------------------------------------


def compute_property_value(
    purchase_price: float | None,
    appraised_value: float | None,
) -> float | None:
    """FNMA rule: property value = min(purchase_price, appraised_value) when both exist."""
    values = [v for v in (purchase_price, appraised_value) if v is not None and v > 0]
    if not values:
        return None
    return min(values)


# ---------------------------------------------------------------------------
# LTV / CLTV
# ---------------------------------------------------------------------------


def compute_ltv(loan_amount: float | None, property_value: float | None) -> float | None:
    """LTV = (loan_amount / property_value) * 100."""
    if not loan_amount or not property_value or property_value <= 0:
        return None
    result = round(loan_amount / property_value * 100, 3)
    # Cap to fit NUMERIC(6,3) column — max 999.999
    return min(result, 999.999)


def compute_cltv(loan_amount: float | None, property_value: float | None) -> float | None:
    """CLTV = same as LTV for now (no subordinate liens tracked)."""
    return compute_ltv(loan_amount, property_value)


# ---------------------------------------------------------------------------
# Qualifying income
# ---------------------------------------------------------------------------


def _income_from_voe(documents: list[Document]) -> float | None:
    """Derive monthly income from VOE_WRITTEN documents."""
    voe_docs = [d for d in documents if d.document_type == DocumentType.VOE_WRITTEN]
    if not voe_docs:
        return None

    total_annual = 0.0
    found_any = False

    for doc in voe_docs:
        base_salary = _safe_float(_get_extracted(doc, "base_salary"))
        pay_freq = _get_extracted(doc, "pay_frequency")
        if base_salary is None:
            continue
        factor = _annualization_factor(pay_freq)
        if factor is None:
            continue
        total_annual += base_salary * factor
        found_any = True

    if not found_any:
        return None
    return round(total_annual / 12, 2)


def _income_from_w2(documents: list[Document]) -> float | None:
    """Derive monthly income from W2 documents (most recent year, sum across employers)."""
    w2_docs = [d for d in documents if d.document_type == DocumentType.W2]
    if not w2_docs:
        return None

    # Group by year, pick the most recent
    by_year: dict[int, list[Document]] = {}
    for doc in w2_docs:
        year = _get_extracted(doc, "year")
        year_int = _safe_int(year)
        if year_int is None:
            # Try to use tax_year from the document model
            if doc.tax_year:
                year_int = doc.tax_year
            else:
                continue
        by_year.setdefault(year_int, []).append(doc)

    if not by_year:
        return None

    most_recent_year = max(by_year.keys())
    total_wages = 0.0
    found_any = False

    for doc in by_year[most_recent_year]:
        wages = _safe_float(_get_extracted(doc, "wages_box1"))
        if wages is not None:
            total_wages += wages
            found_any = True

    if not found_any:
        return None
    return round(total_wages / 12, 2)


def _income_from_paystub_ytd(documents: list[Document]) -> float | None:
    """Derive monthly income from pay stub YTD gross annualized by months elapsed."""
    paystub_docs = [d for d in documents if d.document_type == DocumentType.PAY_STUB]
    if not paystub_docs:
        return None

    # Use the most recent pay stub (by period_end)
    best_doc = None
    best_end: date | None = None
    for doc in paystub_docs:
        ytd = _safe_float(_get_extracted(doc, "gross_pay_ytd"))
        if ytd is None:
            continue
        period_end_raw = _get_extracted(doc, "period_end") or doc.period_end
        if not period_end_raw:
            continue
        try:
            end_date = (
                datetime.strptime(str(period_end_raw), "%Y-%m-%d").date()
                if isinstance(period_end_raw, str)
                else period_end_raw
            )
        except (ValueError, TypeError):
            continue
        if best_end is None or end_date > best_end:
            best_end = end_date
            best_doc = doc

    if best_doc is None or best_end is None:
        return None

    ytd_gross = _safe_float(_get_extracted(best_doc, "gross_pay_ytd"))
    if ytd_gross is None or ytd_gross <= 0:
        return None

    # Months elapsed in the year (including partial month)
    months_elapsed = best_end.month + (best_end.day / 30.0) - 1.0
    if months_elapsed <= 0:
        months_elapsed = 1.0

    annualized = ytd_gross / months_elapsed * 12.0
    return round(annualized / 12, 2)


def _income_from_paystub_current(documents: list[Document]) -> float | None:
    """Derive monthly income from current-period pay stub gross + pay frequency."""
    paystub_docs = [d for d in documents if d.document_type == DocumentType.PAY_STUB]
    if not paystub_docs:
        return None

    total_monthly = 0.0
    found_any = False

    for doc in paystub_docs:
        gross_current = _safe_float(_get_extracted(doc, "gross_pay_current"))
        pay_freq = _get_extracted(doc, "pay_frequency")
        if gross_current is None:
            continue
        factor = _annualization_factor(pay_freq)
        if factor is None:
            continue
        total_monthly += gross_current * factor / 12.0
        found_any = True

    if not found_any:
        return None
    return round(total_monthly, 2)


def compute_qualifying_income_monthly(documents: list[Document]) -> float | None:
    """Compute qualifying monthly income using the priority waterfall.

    Priority:
    1. VOE with base_salary + pay_frequency
    2. W2 wages_box1 (most recent year, summed across employers)
    3. Pay stub gross_pay_ytd annualized
    4. Pay stub gross_pay_current * pay_frequency
    """
    for income_fn in (
        _income_from_voe,
        _income_from_w2,
        _income_from_paystub_ytd,
        _income_from_paystub_current,
    ):
        result = income_fn(documents)
        if result is not None and result > 0:
            return result
    return None


# ---------------------------------------------------------------------------
# Monthly housing expense components
# ---------------------------------------------------------------------------


def compute_pi_payment(
    loan_amount: float | None,
    annual_rate: float | None,
    term_months: int | None,
) -> float | None:
    """Standard amortization P&I: M = P * [r(1+r)^n] / [(1+r)^n - 1]."""
    if not loan_amount or loan_amount <= 0:
        return None
    if not term_months or term_months <= 0:
        return None
    if annual_rate is None or annual_rate < 0:
        return None

    # Handle zero interest rate edge case
    if annual_rate == 0:
        return round(loan_amount / term_months, 2)

    r = annual_rate / 100.0 / 12.0  # monthly rate
    n = term_months
    factor = (1 + r) ** n
    payment = loan_amount * (r * factor) / (factor - 1)
    return round(payment, 2)


def compute_property_tax_monthly(purchase_price: float | None) -> float | None:
    """Estimate monthly property tax: 1.25% annual rate."""
    if not purchase_price or purchase_price <= 0:
        return None
    return round(purchase_price * 0.0125 / 12, 2)


def compute_insurance_monthly(
    documents: list[Document],
    purchase_price: float | None,
) -> float | None:
    """Monthly insurance from HOI doc, or estimate from purchase price."""
    hoi_docs = [d for d in documents if d.document_type == DocumentType.HOI_DECLARATION]
    for doc in hoi_docs:
        annual_premium = _safe_float(_get_extracted(doc, "annual_premium"))
        if annual_premium is not None and annual_premium > 0:
            return round(annual_premium / 12, 2)

    # Fallback estimate: 0.5% of purchase price
    if purchase_price and purchase_price > 0:
        return round(purchase_price * 0.005 / 12, 2)
    return None


def compute_pmi_monthly(
    loan_amount: float | None,
    ltv: float | None,
) -> float:
    """PMI estimate if LTV > 80: 0.5% annual of loan amount."""
    if ltv is None or ltv <= 80:
        return 0.0
    if not loan_amount or loan_amount <= 0:
        return 0.0
    return round(loan_amount * 0.005 / 12, 2)


def compute_monthly_housing_expense(
    pi_payment: float | None,
    property_tax: float | None,
    insurance: float | None,
    pmi: float | None,
) -> float | None:
    """Sum of PITI + PMI. Returns None only if all components are None."""
    components = [pi_payment, property_tax, insurance, pmi]
    non_none = [c for c in components if c is not None]
    if not non_none:
        return None
    return round(sum(non_none), 2)


# ---------------------------------------------------------------------------
# DTI ratios
# ---------------------------------------------------------------------------


def compute_dti_front(
    monthly_housing: float | None,
    qualifying_income: float | None,
) -> float | None:
    """Front-end DTI (housing ratio) = housing / income * 100."""
    if not monthly_housing or not qualifying_income or qualifying_income <= 0:
        return None
    result = round(monthly_housing / qualifying_income * 100, 3)
    # Cap to fit NUMERIC(6,3) column — max 999.999
    return min(result, 999.999)


def compute_dti_back(
    monthly_housing: float | None,
    total_monthly_obligations: float | None,
    qualifying_income: float | None,
) -> float | None:
    """Back-end DTI = (housing + credit obligations) / income * 100."""
    if not qualifying_income or qualifying_income <= 0:
        return None
    housing = monthly_housing or 0.0
    obligations = total_monthly_obligations or 0.0
    total = housing + obligations
    if total <= 0:
        return None
    result = round(total / qualifying_income * 100, 3)
    # Cap to fit NUMERIC(6,3) column — max 999.999
    return min(result, 999.999)


# ---------------------------------------------------------------------------
# Credit scores
# ---------------------------------------------------------------------------


def extract_credit_scores(
    documents: list[Document],
) -> tuple[int | None, int | None, int | None]:
    """Extract credit scores from CREDIT_REPORT documents.

    Returns (borrower_score, coborrower_score, representative_score).
    For a single borrower, representative = borrower score.
    For multiple borrowers, representative = min of the two middle scores (FNMA rule).
    """
    credit_docs = [d for d in documents if d.document_type == DocumentType.CREDIT_REPORT]
    if not credit_docs:
        return None, None, None

    borrower_score: int | None = None
    coborrower_score: int | None = None

    for doc in credit_docs:
        score = _safe_int(_get_extracted(doc, "representative_score"))
        if score is None:
            continue

        # Determine if this is a coborrower credit report by checking borrower association
        # or by order encountered (first = borrower, second = coborrower)
        if borrower_score is None:
            borrower_score = score
        elif coborrower_score is None:
            coborrower_score = score

    if borrower_score is None:
        return None, None, None

    if coborrower_score is not None:
        representative = min(borrower_score, coborrower_score)
    else:
        representative = borrower_score

    return borrower_score, coborrower_score, representative


# ---------------------------------------------------------------------------
# Total monthly obligations from credit report
# ---------------------------------------------------------------------------


def extract_total_monthly_payments(documents: list[Document]) -> float | None:
    """Extract total_monthly_payments from the first CREDIT_REPORT with the field."""
    credit_docs = [d for d in documents if d.document_type == DocumentType.CREDIT_REPORT]
    for doc in credit_docs:
        val = _safe_float(_get_extracted(doc, "total_monthly_payments"))
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# Appraised value proxy
# ---------------------------------------------------------------------------


def extract_appraised_value_proxy(
    documents: list[Document],
    existing_appraised: float | None,
) -> float | None:
    """Use PURCHASE_CONTRACT purchase_price as appraised value proxy if none is set."""
    if existing_appraised is not None and existing_appraised > 0:
        return existing_appraised

    contract_docs = [
        d for d in documents if d.document_type == DocumentType.PURCHASE_CONTRACT
    ]
    for doc in contract_docs:
        price = _safe_float(_get_extracted(doc, "purchase_price"))
        if price is not None and price > 0:
            return price
    return existing_appraised


# ---------------------------------------------------------------------------
# AI readiness score
# ---------------------------------------------------------------------------


def _checklist_completion_pct(
    documents: list[Document],
    loan: Loan,
) -> float:
    """Percentage of required checklist items that have a processed document."""
    checklist = generate_checklist(
        persona=loan.primary_borrower_persona,
        loan_purpose=loan.loan_purpose,
        occupancy_type=loan.occupancy_type,
        property_type=loan.property_type,
    )
    if not checklist:
        return 0.0

    required_types = {
        item["document_type"]
        for item in checklist
        if item.get("required", False)
    }
    if not required_types:
        return 100.0

    received_types = {
        d.document_type
        for d in documents
        if d.document_type is not None and d.status in _PROCESSED_STATUSES
    }

    matched = required_types & received_types
    return len(matched) / len(required_types) * 100.0


def _validation_confidence(validations: list[AgentValidation]) -> float:
    """Latest cross-doc validation confidence score (0-100 scale)."""
    if not validations:
        return 0.0

    # Find the most recent validation by created_at
    latest = max(validations, key=lambda v: v.created_at if v.created_at else datetime.min)
    score = float(latest.confidence_score)
    # confidence_score is stored as 0.0-1.0, convert to 0-100
    return min(score * 100.0, 100.0)


def _key_metrics_populated_pct(
    ltv: float | None,
    dti_front: float | None,
    dti_back: float | None,
    credit_score: int | None,
    income: float | None,
) -> float:
    """Percentage of key underwriting metrics that are populated (0-100)."""
    metrics = [ltv, dti_front, dti_back, credit_score, income]
    populated = sum(1 for m in metrics if m is not None)
    return populated / len(metrics) * 100.0


def _document_freshness_pct(documents: list[Document]) -> float:
    """Percentage of documents that are within their freshness window."""
    today = date.today()
    checked = 0
    fresh = 0

    for doc in documents:
        if doc.document_type not in _FRESHNESS_WINDOWS:
            continue
        window_days = _FRESHNESS_WINDOWS[doc.document_type]
        checked += 1

        # Use period_end or created_at to determine age
        doc_date: date | None = None
        if doc.period_end:
            try:
                doc_date = datetime.strptime(doc.period_end, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass
        if doc_date is None and doc.created_at:
            doc_date = (
                doc.created_at.date()
                if isinstance(doc.created_at, datetime)
                else doc.created_at
            )
        if doc_date is None:
            continue

        age_days = (today - doc_date).days
        if age_days <= window_days:
            fresh += 1

    if checked == 0:
        return 100.0  # No time-sensitive docs to evaluate
    return fresh / checked * 100.0


def _conditions_clear_rate(conditions: list[Condition]) -> float:
    """Percentage of conditions that are cleared or waived."""
    if not conditions:
        return 100.0  # No conditions is a good state
    cleared = sum(
        1 for c in conditions
        if c.status in (ConditionStatus.CLEARED, ConditionStatus.WAIVED)
    )
    return cleared / len(conditions) * 100.0


def compute_ai_readiness_score(
    documents: list[Document],
    loan: Loan,
    validations: list[AgentValidation],
    conditions: list[Condition],
    ltv: float | None,
    dti_front: float | None,
    dti_back: float | None,
    credit_score: int | None,
    income: float | None,
) -> float:
    """Weighted composite AI readiness score (0-100).

    Weights:
        Checklist completion:     30%
        Validation confidence:    25%
        Key metrics populated:    20%
        Document freshness:       15%
        Conditions clear rate:    10%
    """
    checklist_pct = _checklist_completion_pct(documents, loan)
    validation_pct = _validation_confidence(validations)
    metrics_pct = _key_metrics_populated_pct(ltv, dti_front, dti_back, credit_score, income)
    freshness_pct = _document_freshness_pct(documents)
    conditions_pct = _conditions_clear_rate(conditions)

    score = (
        checklist_pct * 0.30
        + validation_pct * 0.25
        + metrics_pct * 0.20
        + freshness_pct * 0.15
        + conditions_pct * 0.10
    )
    return round(min(max(score, 0.0), 100.0), 2)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def recalculate_loan_metrics(loan_id: str) -> dict:
    """Recalculate all loan metrics from documents and loan fields.

    Loads the loan with all related documents, validations, and conditions,
    computes every metric, persists changes, and broadcasts an SSE event.

    Returns a dict of all updated metric values.
    """
    async with get_db_session() as session:
        # Load loan
        loan_result = await session.execute(
            select(Loan).where(Loan.id == loan_id)
        )
        loan = loan_result.scalar_one_or_none()
        if loan is None:
            logger.error("recalculate_loan_metrics: loan %s not found", loan_id)
            return {}

        # Load related entities
        docs_result = await session.execute(
            select(Document).where(Document.loan_id == loan_id)
        )
        documents: list[Document] = list(docs_result.scalars().all())

        validations_result = await session.execute(
            select(AgentValidation)
            .where(AgentValidation.loan_id == loan_id)
            .order_by(AgentValidation.created_at.desc())
        )
        validations: list[AgentValidation] = list(validations_result.scalars().all())

        conditions_result = await session.execute(
            select(Condition).where(Condition.loan_id == loan_id)
        )
        conditions: list[Condition] = list(conditions_result.scalars().all())

        logger.info(
            "recalculate_loan_metrics: loan=%s docs=%d validations=%d conditions=%d",
            loan_id,
            len(documents),
            len(validations),
            len(conditions),
        )

        # ----- Appraised value proxy -----
        appraised_value = extract_appraised_value_proxy(documents, loan.appraised_value)
        if appraised_value != loan.appraised_value:
            loan.appraised_value = appraised_value

        # Also extract purchase_price from contract if not already on the loan
        purchase_price = loan.purchase_price
        if not purchase_price:
            contract_docs = [
                d for d in documents
                if d.document_type == DocumentType.PURCHASE_CONTRACT
            ]
            for doc in contract_docs:
                pp = _safe_float(_get_extracted(doc, "purchase_price"))
                if pp is not None and pp > 0:
                    purchase_price = pp
                    loan.purchase_price = purchase_price
                    break

        # ----- Property value & LTV -----
        property_value = compute_property_value(
            purchase_price=float(loan.purchase_price) if loan.purchase_price else None,
            appraised_value=float(loan.appraised_value) if loan.appraised_value else None,
        )
        loan_amount = float(loan.loan_amount) if loan.loan_amount else None

        ltv = compute_ltv(loan_amount, property_value)
        cltv = compute_cltv(loan_amount, property_value)
        loan.ltv = ltv
        loan.cltv = cltv

        # ----- Qualifying income -----
        qualifying_income = compute_qualifying_income_monthly(documents)
        loan.qualifying_income_monthly = qualifying_income

        # ----- Credit scores -----
        borrower_score, coborrower_score, representative_score = extract_credit_scores(
            documents
        )
        loan.credit_score_borrower = borrower_score
        loan.credit_score_coborrower = coborrower_score
        loan.representative_credit_score = representative_score

        # ----- Monthly housing expense components -----
        interest_rate = float(loan.interest_rate) if loan.interest_rate else None
        term_months = loan.loan_term_months

        pi_payment = compute_pi_payment(loan_amount, interest_rate, term_months)
        property_tax = compute_property_tax_monthly(
            float(loan.purchase_price) if loan.purchase_price else None
        )
        insurance = compute_insurance_monthly(
            documents,
            float(loan.purchase_price) if loan.purchase_price else None,
        )
        pmi = compute_pmi_monthly(loan_amount, ltv)
        monthly_housing = compute_monthly_housing_expense(
            pi_payment, property_tax, insurance, pmi
        )

        # ----- DTI ratios -----
        total_monthly_payments = extract_total_monthly_payments(documents)

        dti_front = compute_dti_front(monthly_housing, qualifying_income)
        dti_back = compute_dti_back(
            monthly_housing, total_monthly_payments, qualifying_income
        )
        loan.dti_front = dti_front
        loan.dti_back = dti_back

        # ----- AI readiness score -----
        ai_readiness = compute_ai_readiness_score(
            documents=documents,
            loan=loan,
            validations=validations,
            conditions=conditions,
            ltv=ltv,
            dti_front=dti_front,
            dti_back=dti_back,
            credit_score=representative_score,
            income=qualifying_income,
        )
        loan.ai_readiness_score = ai_readiness

        # Flush to DB (session commit is handled by get_db_session context manager)
        session.add(loan)
        await session.flush()

        # Build result dict
        metrics = {
            "loan_id": str(loan_id),
            "ltv": float(ltv) if ltv is not None else None,
            "cltv": float(cltv) if cltv is not None else None,
            "qualifying_income_monthly": (
                float(qualifying_income) if qualifying_income is not None else None
            ),
            "dti_front": float(dti_front) if dti_front is not None else None,
            "dti_back": float(dti_back) if dti_back is not None else None,
            "credit_score_borrower": borrower_score,
            "credit_score_coborrower": coborrower_score,
            "representative_credit_score": representative_score,
            "ai_readiness_score": float(ai_readiness),
            "appraised_value": (
                float(loan.appraised_value) if loan.appraised_value else None
            ),
            "purchase_price": (
                float(loan.purchase_price) if loan.purchase_price else None
            ),
            "monthly_housing_expense": (
                float(monthly_housing) if monthly_housing is not None else None
            ),
            "pi_payment": float(pi_payment) if pi_payment is not None else None,
            "total_monthly_obligations": (
                float(total_monthly_payments)
                if total_monthly_payments is not None
                else None
            ),
        }

        logger.info(
            "recalculate_loan_metrics: loan=%s ltv=%s dti_front=%s dti_back=%s "
            "income=%s credit=%s readiness=%s",
            loan_id,
            ltv,
            dti_front,
            dti_back,
            qualifying_income,
            representative_score,
            ai_readiness,
        )

    # Broadcast SSE event (outside the DB session)
    await broadcast_loan_event(
        loan_id=str(loan_id),
        event_type="loan_metrics_updated",
        data=metrics,
    )

    return metrics
