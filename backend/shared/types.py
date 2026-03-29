from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    LOAN_OFFICER = "loan_officer"
    UNDERWRITER = "underwriter"
    PROCESSOR = "processor"
    BORROWER = "borrower"


class BorrowerPersona(StrEnum):
    W2_SALARIED = "w2_salaried"
    SELF_EMPLOYED = "self_employed"
    COMMISSION_VARIABLE = "commission_variable"
    RETIRED_FIXED = "retired_fixed"
    RENTAL_INCOME = "rental_income"


class LoanStatus(StrEnum):
    CREATED = "created"
    INTAKE = "intake"
    PROCESSING = "processing"
    SUBMITTED_TO_UW = "submitted_to_uw"
    CONDITIONALLY_APPROVED = "conditionally_approved"
    CLEAR_TO_CLOSE = "clear_to_close"
    CLOSING = "closing"
    FUNDED = "funded"
    SUSPENDED = "suspended"
    DENIED = "denied"


class ProcessingPhase(StrEnum):
    INTAKE = "phase_0_intake"
    AUS_CREDIT = "phase_1_aus_credit"
    DOC_COLLECTION = "phase_2_doc_collection"
    DATA_VERIFICATION = "phase_3_data_verification"
    THIRD_PARTY = "phase_4_third_party"
    UW_SUBMISSION = "phase_5_uw_submission"
    CLOSING = "phase_6_closing"


class DocumentType(StrEnum):
    # Income docs
    W2 = "w2"
    PAY_STUB = "pay_stub"
    TAX_RETURN_1040 = "tax_return_1040"
    TAX_RETURN_BUSINESS = "tax_return_business"
    SCHEDULE_C = "schedule_c"
    SCHEDULE_E = "schedule_e"
    K1 = "k1"
    FORM_1099 = "form_1099"
    FORM_1099_R = "form_1099_r"
    PL_STATEMENT = "pl_statement"
    BALANCE_SHEET = "balance_sheet"
    BUSINESS_LICENSE = "business_license"
    CPA_LETTER = "cpa_letter"
    EMPLOYMENT_CONTRACT = "employment_contract"
    SS_AWARD_LETTER = "ss_award_letter"
    PENSION_STATEMENT = "pension_statement"
    # Asset docs
    BANK_STATEMENT = "bank_statement"
    RETIREMENT_STATEMENT = "retirement_statement"
    GIFT_LETTER = "gift_letter"
    EARNEST_MONEY_RECEIPT = "earnest_money_receipt"
    # Employment
    VOE_VERBAL = "voe_verbal"
    VOE_WRITTEN = "voe_written"
    # Credit
    CREDIT_REPORT = "credit_report"
    LOE_CREDIT = "loe_credit"
    # Property
    PURCHASE_CONTRACT = "purchase_contract"
    APPRAISAL = "appraisal"
    TITLE_COMMITMENT = "title_commitment"
    HOI_DECLARATION = "hoi_declaration"
    FLOOD_CERT = "flood_cert"
    HOA_DOCS = "hoa_docs"
    CONDO_QUESTIONNAIRE = "condo_questionnaire"
    LEASE_AGREEMENT = "lease_agreement"
    MORTGAGE_STATEMENT = "mortgage_statement"
    PROPERTY_TAX_BILL = "property_tax_bill"
    # Legal/Compliance
    PHOTO_ID = "photo_id"
    SSN_AUTHORIZATION = "ssn_authorization"
    FORM_4506_C = "form_4506_c"
    IRS_TRANSCRIPT = "irs_transcript"
    DIVORCE_DECREE = "divorce_decree"
    CHILD_SUPPORT_ORDER = "child_support_order"
    BANKRUPTCY_DISCHARGE = "bankruptcy_discharge"
    LOE_GENERAL = "loe_general"
    # Closing
    CLOSING_DISCLOSURE = "closing_disclosure"
    LOAN_ESTIMATE = "loan_estimate"
    # Other
    OTHER = "other"


class DocumentCategory(StrEnum):
    INCOME = "income"
    ASSETS = "assets"
    PROPERTY = "property"
    TITLE = "title"
    INSURANCE = "insurance"
    CREDIT = "credit"
    LEGAL = "legal"
    COMPLIANCE = "compliance"
    CLOSING = "closing"
    OTHER = "other"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    CLASSIFYING = "classifying"
    CLASSIFIED = "classified"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    VALIDATING = "validating"
    VALIDATED = "validated"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class ConditionType(StrEnum):
    PTD = "prior_to_doc"
    PTF = "prior_to_funding"
    PTC = "prior_to_closing"
    POST_CLOSING = "post_closing"


class ConditionSource(StrEnum):
    AUS = "aus"
    UNDERWRITER = "underwriter"
    SYSTEM = "system"
    COMPLIANCE = "compliance"


class ConditionStatus(StrEnum):
    OPEN = "open"
    REQUESTED = "requested"
    RECEIVED = "received"
    REVIEWED = "reviewed"
    CLEARED = "cleared"
    WAIVED = "waived"


class ConfidenceLevel(StrEnum):
    HIGH = "high"          # 0.90-1.0
    MEDIUM = "medium"      # 0.70-0.89
    LOW = "low"            # 0.50-0.69
    ESCALATE = "escalate"  # <0.50


class MessageType(StrEnum):
    NEEDS_LIST = "needs_list"
    CLARIFICATION = "clarification"
    STATUS_UPDATE = "status_update"
    ESCALATION = "escalation"
    LOE_REQUEST = "loe_request"
    DOC_DEFICIENCY = "doc_deficiency"


class ServiceOrderType(StrEnum):
    CREDIT = "credit"
    AUS_DU = "aus_du"
    AUS_LP = "aus_lp"
    APPRAISAL = "appraisal"
    TITLE = "title"
    FLOOD = "flood"
    HOI = "hoi"
    PMI = "pmi"
    VOE = "voe"
    FORM_4506_C = "form_4506_c"


def confidence_level_from_score(score: float) -> ConfidenceLevel:
    if score >= 0.90:
        return ConfidenceLevel.HIGH
    elif score >= 0.70:
        return ConfidenceLevel.MEDIUM
    elif score >= 0.50:
        return ConfidenceLevel.LOW
    else:
        return ConfidenceLevel.ESCALATE
