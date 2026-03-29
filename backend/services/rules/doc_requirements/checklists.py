"""
Persona-based document checklist generator for conventional loans.
Maps borrower persona + loan parameters to required documents per FNMA Selling Guide.
"""

from ...shared.types import BorrowerPersona, DocumentCategory, DocumentType


def classify_persona(
    employment_type: str | None = None,
    self_employed: bool | None = None,
    ownership_percentage: float | None = None,
    income_sources: dict | None = None,
) -> BorrowerPersona:
    """Classify borrower persona from 1003 application data."""
    income_sources = income_sources or {}

    # Self-employed: 25%+ ownership or explicit flag
    if self_employed or (ownership_percentage and ownership_percentage >= 25):
        return BorrowerPersona.SELF_EMPLOYED

    # Retired: SS/pension income, no current employment
    retirement_indicators = {"social_security", "pension", "retirement_distribution"}
    if income_sources and retirement_indicators.intersection(income_sources.keys()):
        has_employment_income = any(
            k in income_sources for k in ("base_salary", "commission", "bonus", "overtime")
        )
        if not has_employment_income:
            return BorrowerPersona.RETIRED_FIXED

    # Rental income: Schedule E income or RE owned
    if income_sources and "rental_income" in income_sources:
        return BorrowerPersona.RENTAL_INCOME

    # Commission/Variable: >25% of income from commission/bonus/OT
    if employment_type in ("commission", "variable"):
        return BorrowerPersona.COMMISSION_VARIABLE
    if income_sources:
        total = sum(v for v in income_sources.values() if isinstance(v, (int, float)))
        variable = sum(
            income_sources.get(k, 0)
            for k in ("commission", "bonus", "overtime")
            if isinstance(income_sources.get(k, 0), (int, float))
        )
        if total > 0 and variable / total > 0.25:
            return BorrowerPersona.COMMISSION_VARIABLE

    # Default: W-2 salaried
    return BorrowerPersona.W2_SALARIED


# --- Document requirement definitions ---

_UNIVERSAL_DOCS = [
    {
        "document_type": DocumentType.BANK_STATEMENT,
        "category": DocumentCategory.ASSETS,
        "label": "Bank Statements (2 months, all accounts)",
        "required": True,
        "description": "Most recent 2 months for all checking, savings, and money market accounts",
    },
    {
        "document_type": DocumentType.CREDIT_REPORT,
        "category": DocumentCategory.CREDIT,
        "label": "Tri-Merge Credit Report",
        "required": True,
        "description": "Pulled by system via credit service order",
    },
    {
        "document_type": DocumentType.PHOTO_ID,
        "category": DocumentCategory.COMPLIANCE,
        "label": "Government-Issued Photo ID",
        "required": True,
        "description": "Valid driver's license, passport, or state ID",
    },
    {
        "document_type": DocumentType.SSN_AUTHORIZATION,
        "category": DocumentCategory.COMPLIANCE,
        "label": "SSN Authorization",
        "required": True,
        "description": "Authorization to verify SSN",
    },
    {
        "document_type": DocumentType.FORM_4506_C,
        "category": DocumentCategory.COMPLIANCE,
        "label": "4506-C IRS Tax Transcript Authorization",
        "required": True,
        "description": "Signed authorization for IRS tax transcripts",
    },
]

_PURCHASE_DOCS = [
    {
        "document_type": DocumentType.PURCHASE_CONTRACT,
        "category": DocumentCategory.PROPERTY,
        "label": "Purchase Agreement / Sales Contract",
        "required": True,
        "description": "Fully executed purchase contract with all addenda",
    },
    {
        "document_type": DocumentType.EARNEST_MONEY_RECEIPT,
        "category": DocumentCategory.ASSETS,
        "label": "Earnest Money Deposit Receipt",
        "required": True,
        "description": "Proof of earnest money deposit",
    },
]

_REFI_DOCS = [
    {
        "document_type": DocumentType.MORTGAGE_STATEMENT,
        "category": DocumentCategory.PROPERTY,
        "label": "Current Mortgage Statement",
        "required": True,
        "description": "Most recent mortgage statement showing balance and payment",
    },
]

_HOI_DOCS = [
    {
        "document_type": DocumentType.HOI_DECLARATION,
        "category": DocumentCategory.INSURANCE,
        "label": "Homeowners Insurance Declarations Page",
        "required": True,
        "description": "Current declarations page showing coverage amounts and effective dates",
    },
]

_W2_DOCS = [
    {
        "document_type": DocumentType.W2,
        "category": DocumentCategory.INCOME,
        "label": "W-2s (2 years)",
        "required": True,
        "description": "W-2 wage statements from all employers for most recent 2 years",
    },
    {
        "document_type": DocumentType.PAY_STUB,
        "category": DocumentCategory.INCOME,
        "label": "Pay Stubs (30 days most recent)",
        "required": True,
        "description": "Most recent 30 days of pay stubs from all employers",
    },
    {
        "document_type": DocumentType.VOE_WRITTEN,
        "category": DocumentCategory.INCOME,
        "label": "Verification of Employment (VOE)",
        "required": True,
        "description": "Verbal or written VOE from current employer(s)",
    },
]

_SELF_EMPLOYED_DOCS = [
    {
        "document_type": DocumentType.TAX_RETURN_1040,
        "category": DocumentCategory.INCOME,
        "label": "Personal Tax Returns (2 years with all schedules)",
        "required": True,
        "description": "Complete federal personal tax returns (1040) with all schedules for 2 years",
    },
    {
        "document_type": DocumentType.TAX_RETURN_BUSINESS,
        "category": DocumentCategory.INCOME,
        "label": "Business Tax Returns (2 years)",
        "required": True,
        "description": "Complete business tax returns (1120S, 1065, or Schedule C) for 2 years",
    },
    {
        "document_type": DocumentType.PL_STATEMENT,
        "category": DocumentCategory.INCOME,
        "label": "Year-to-Date Profit & Loss Statement",
        "required": True,
        "description": "YTD P&L statement (CPA-prepared if past Q3)",
    },
    {
        "document_type": DocumentType.BALANCE_SHEET,
        "category": DocumentCategory.INCOME,
        "label": "Year-to-Date Balance Sheet",
        "required": True,
        "description": "YTD balance sheet for the business",
    },
    {
        "document_type": DocumentType.BUSINESS_LICENSE,
        "category": DocumentCategory.INCOME,
        "label": "Business License or CPA Letter",
        "required": True,
        "description": "Proof of business existence - business license, CPA letter, or Articles of Incorporation",
    },
    {
        "document_type": DocumentType.K1,
        "category": DocumentCategory.INCOME,
        "label": "K-1 Partnership/S-Corp Forms",
        "required": True,
        "description": "K-1 forms from partnerships or S-corporations (2 years)",
    },
]

_COMMISSION_DOCS = [
    {
        "document_type": DocumentType.W2,
        "category": DocumentCategory.INCOME,
        "label": "W-2s (2 years - for income trending)",
        "required": True,
        "description": "W-2s from 2 most recent years to analyze YoY income trending",
    },
    {
        "document_type": DocumentType.TAX_RETURN_1040,
        "category": DocumentCategory.INCOME,
        "label": "Personal Tax Returns (2 years for 2-year average)",
        "required": True,
        "description": "Complete 1040 returns needed for 2-year income averaging per FNMA",
    },
    {
        "document_type": DocumentType.PAY_STUB,
        "category": DocumentCategory.INCOME,
        "label": "Pay Stubs (30 days with YTD breakdown)",
        "required": True,
        "description": "Pay stubs showing base vs commission vs bonus vs OT breakdown",
    },
    {
        "document_type": DocumentType.VOE_WRITTEN,
        "category": DocumentCategory.INCOME,
        "label": "Written VOE (with income breakdown)",
        "required": True,
        "description": "Written VOE detailing base, commission, bonus, and overtime separately",
    },
    {
        "document_type": DocumentType.EMPLOYMENT_CONTRACT,
        "category": DocumentCategory.INCOME,
        "label": "Employment Contract",
        "required": False,
        "description": "Required if newly hired in a commission-based role",
    },
]

_RETIRED_DOCS = [
    {
        "document_type": DocumentType.SS_AWARD_LETTER,
        "category": DocumentCategory.INCOME,
        "label": "Social Security Award Letter",
        "required": True,
        "description": "Current year Social Security benefit verification letter",
    },
    {
        "document_type": DocumentType.PENSION_STATEMENT,
        "category": DocumentCategory.INCOME,
        "label": "Pension/Annuity Statements",
        "required": True,
        "description": "Most recent pension or annuity statements",
    },
    {
        "document_type": DocumentType.FORM_1099_R,
        "category": DocumentCategory.INCOME,
        "label": "1099-R / 1099-SSA",
        "required": True,
        "description": "1099-R for retirement distributions, 1099-SSA for Social Security",
    },
    {
        "document_type": DocumentType.RETIREMENT_STATEMENT,
        "category": DocumentCategory.ASSETS,
        "label": "Retirement Account Statements (60 days)",
        "required": True,
        "description": "Most recent 60 days of 401k, IRA, or other retirement accounts",
    },
    {
        "document_type": DocumentType.TAX_RETURN_1040,
        "category": DocumentCategory.INCOME,
        "label": "Personal Tax Returns (1-2 years)",
        "required": True,
        "description": "Federal tax returns to verify income sources",
    },
]

_RENTAL_INCOME_DOCS = [
    {
        "document_type": DocumentType.SCHEDULE_E,
        "category": DocumentCategory.INCOME,
        "label": "Schedule E (2 years from tax returns)",
        "required": True,
        "description": "Schedule E showing rental income/loss for all properties (2 years)",
    },
    {
        "document_type": DocumentType.LEASE_AGREEMENT,
        "category": DocumentCategory.INCOME,
        "label": "Current Lease Agreements (all properties)",
        "required": True,
        "description": "Fully executed lease agreements for all rental properties",
    },
    {
        "document_type": DocumentType.MORTGAGE_STATEMENT,
        "category": DocumentCategory.PROPERTY,
        "label": "Mortgage Statements (all RE owned)",
        "required": True,
        "description": "Current mortgage statements for all real estate owned",
    },
    {
        "document_type": DocumentType.HOI_DECLARATION,
        "category": DocumentCategory.INSURANCE,
        "label": "Insurance Declarations (all properties)",
        "required": True,
        "description": "Insurance declarations pages for all rental properties",
    },
    {
        "document_type": DocumentType.PROPERTY_TAX_BILL,
        "category": DocumentCategory.PROPERTY,
        "label": "Property Tax Bills",
        "required": True,
        "description": "Most recent property tax bills for all RE owned",
    },
    {
        "document_type": DocumentType.TAX_RETURN_1040,
        "category": DocumentCategory.INCOME,
        "label": "Personal Tax Returns (2 years with Schedule E)",
        "required": True,
        "description": "Complete 1040 returns with all schedules for rental income calculation",
    },
]

_PERSONA_DOCS: dict[BorrowerPersona, list[dict]] = {
    BorrowerPersona.W2_SALARIED: _W2_DOCS,
    BorrowerPersona.SELF_EMPLOYED: _SELF_EMPLOYED_DOCS,
    BorrowerPersona.COMMISSION_VARIABLE: _COMMISSION_DOCS,
    BorrowerPersona.RETIRED_FIXED: _RETIRED_DOCS,
    BorrowerPersona.RENTAL_INCOME: _RENTAL_INCOME_DOCS,
}


def generate_checklist(
    persona: BorrowerPersona | None,
    loan_purpose: str | None = None,
    occupancy_type: str | None = None,
    property_type: str | None = None,
    has_coborrower: bool = False,
    has_gift_funds: bool = False,
) -> list[dict]:
    """Generate a complete document checklist based on borrower persona and loan parameters."""
    checklist = []

    # Universal docs (always required)
    checklist.extend(_UNIVERSAL_DOCS)

    # Persona-specific income docs
    if persona and persona in _PERSONA_DOCS:
        checklist.extend(_PERSONA_DOCS[persona])
    else:
        # Default to W-2 if unknown
        checklist.extend(_W2_DOCS)

    # Loan purpose specific
    if loan_purpose == "purchase":
        checklist.extend(_PURCHASE_DOCS)
    elif loan_purpose in ("refinance", "cashout_refi"):
        checklist.extend(_REFI_DOCS)

    # HOI always needed
    checklist.extend(_HOI_DOCS)

    # Condo docs
    if property_type == "condo":
        checklist.append({
            "document_type": DocumentType.HOA_DOCS,
            "category": DocumentCategory.PROPERTY,
            "label": "HOA Documents",
            "required": True,
            "description": "HOA budget, bylaws, and master insurance",
        })
        checklist.append({
            "document_type": DocumentType.CONDO_QUESTIONNAIRE,
            "category": DocumentCategory.PROPERTY,
            "label": "Condo Questionnaire",
            "required": True,
            "description": "FNMA warrantability questionnaire",
        })

    # Gift funds
    if has_gift_funds:
        checklist.append({
            "document_type": DocumentType.GIFT_LETTER,
            "category": DocumentCategory.ASSETS,
            "label": "Gift Letter + Source Documentation",
            "required": True,
            "description": "Gift letter signed by donor + proof of donor's ability to give + transfer trail",
        })

    # Deduplicate by document_type (keep first occurrence)
    seen = set()
    deduped = []
    for item in checklist:
        dt = item["document_type"]
        if dt not in seen:
            seen.add(dt)
            deduped.append(item)

    return deduped
