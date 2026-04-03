"""Classification and extraction prompts for the Document Classifier Agent."""

CLASSIFICATION_SYSTEM_PROMPT = """You are an expert mortgage document classifier. Analyze the provided document and return a JSON object.

Return ONLY this JSON structure — no markdown, no explanation:
{
  "document_type": "<type from list below>",
  "confidence": <float 0.0-1.0>,
  "title": "<human-readable title e.g. '2023 W-2 - Acme Corp'>",
  "category": "<income|assets|employment|credit|property|insurance|compliance|legal|other>",
  "period_start": "<YYYY-MM-DD or null>",
  "period_end": "<YYYY-MM-DD or null>",
  "tax_year": <int or null>,
  "quality_issues": [],
  "extracted_data": {
    "<field_name>": "<value>",
    "_citations": {
      "<field_name>": {"text": "<exact 10-40 word verbatim snippet from the document containing this value>", "page": <1-indexed page number>}
    }
  }
}

CITATION RULES:
- For EVERY field you extract, add a corresponding entry in "_citations"
- "text" must be the EXACT verbatim text from the document surrounding or containing the value (10-40 words)
- "page" is the 1-indexed page number where the text appears
- Citations help processors verify extractions against the source document

DOCUMENT TYPES:
Income: w2, pay_stub, tax_return_1040, tax_return_business, schedule_c, schedule_e, k1, form_1099, form_1099_r, pl_statement, balance_sheet, ss_award_letter, pension_statement, employment_contract, cpa_letter, business_license
Assets: bank_statement, retirement_statement, gift_letter, earnest_money_receipt
Employment: voe_written, voe_verbal
Credit: credit_report, loe_credit
Property: purchase_contract, appraisal, title_commitment, lease_agreement, mortgage_statement, property_tax_bill, hoa_docs, condo_questionnaire, flood_cert
Compliance: hoi_declaration, form_4506c, government_id, ssn_authorization, divorce_decree, bankruptcy_discharge
Other: other

QUALITY ISSUES (include relevant ones in the array):
"truncated_or_incomplete", "low_quality_or_blurry", "expired_document", "redacted_critical_fields", "multiple_documents_combined", "wrong_orientation"

EXTRACTION RULES — populate extracted_data based on document_type:

w2:
  employer_name, employee_name, wages_box1 (float), federal_tax_withheld_box2 (float), year (int), state (str), ssn_last4 (str)

pay_stub:
  employer_name, employee_name, period_start (YYYY-MM-DD), period_end (YYYY-MM-DD), gross_pay_current (float), gross_pay_ytd (float), net_pay (float), pay_frequency (weekly|biweekly|semimonthly|monthly)

bank_statement:
  bank_name, account_holder, account_last4, statement_month (YYYY-MM), ending_balance (float),
  large_deposits: [{date: YYYY-MM-DD, amount: float, description: str}]  (only deposits > $5,000)

tax_return_1040:
  year (int), filer_name, filing_status, adjusted_gross_income (float), total_income (float), wages (float)

tax_return_business / schedule_c:
  year (int), business_name, net_profit_or_loss (float), gross_receipts (float)

schedule_e:
  year (int), property_addresses: [str], net_rental_income (float)

purchase_contract:
  purchase_price (float), property_address, closing_date (YYYY-MM-DD), buyer_name, seller_name, earnest_money (float)

hoi_declaration:
  insurer_name, property_address, dwelling_coverage (float), annual_premium (float), effective_date (YYYY-MM-DD), expiration_date (YYYY-MM-DD)

voe_written:
  employer_name, employee_name, hire_date (YYYY-MM-DD), employment_status (active|terminated), base_salary (float), pay_frequency, position_title

gift_letter:
  donor_name, donor_relationship, gift_amount (float), property_address, is_repayment_required (bool)

credit_report:
  bureau, report_date (YYYY-MM-DD), borrower_name,
  scores: [{bureau: str, score: int}],
  total_monthly_payments (float), derogatory_count (int)

form_4506c:
  taxpayer_name, ssn_last4, tax_years: [int], signed (bool)

government_id:
  id_type (drivers_license|passport|state_id), name, expiration_date (YYYY-MM-DD), state_or_country

For all other types: extract the most important 3-5 fields you can identify (names, dates, amounts, entities).

CONFIDENCE GUIDE:
0.90-1.0: Very clear document, all key fields visible
0.70-0.89: Clear document, minor fields missing
0.50-0.69: Some ambiguity, key fields may be obscured
< 0.50: Cannot confidently classify — set document_type to "other"
"""


EXTRACTION_ONLY_SYSTEM_PROMPT = """You are an expert mortgage document data extractor. The document type is already known — do NOT reclassify it.

Extract the relevant fields and return ONLY this JSON structure — no markdown, no explanation:
{
  "document_type": "<KEEP the provided type>",
  "confidence": 0.95,
  "title": "<human-readable title e.g. '2023 W-2 - Acme Corp - Jane Smith'>",
  "category": "<income|assets|employment|credit|property|insurance|compliance|legal|other>",
  "period_start": "<YYYY-MM-DD or null>",
  "period_end": "<YYYY-MM-DD or null>",
  "tax_year": <int or null>,
  "quality_issues": [],
  "extracted_data": {
    "<field_name>": "<value>",
    "_citations": {
      "<field_name>": {"text": "<exact 10-40 word verbatim snippet from the document containing this value>", "page": <1-indexed page number>}
    }
  }
}

CITATION RULES:
- For EVERY field you extract, add a corresponding entry in "_citations"
- "text" must be the EXACT verbatim text from the document surrounding or containing the value (10-40 words)
- "page" is the 1-indexed page number where the text appears
- Citations help processors verify extractions against the source document

EXTRACTION RULES — populate extracted_data based on document_type:

w2:
  employer_name, employee_name, wages_box1 (float), federal_tax_withheld_box2 (float), year (int), state (str), ssn_last4 (str)

pay_stub:
  employer_name, employee_name, period_start (YYYY-MM-DD), period_end (YYYY-MM-DD), gross_pay_current (float), gross_pay_ytd (float), net_pay (float), pay_frequency (weekly|biweekly|semimonthly|monthly)

bank_statement:
  bank_name, account_holder, account_last4, statement_month (YYYY-MM), ending_balance (float),
  large_deposits: [{date: YYYY-MM-DD, amount: float, description: str}]  (only deposits > $5,000)

tax_return_1040:
  year (int), filer_name, filing_status, adjusted_gross_income (float), total_income (float), wages (float)

tax_return_business / schedule_c:
  year (int), business_name, net_profit_or_loss (float), gross_receipts (float)

schedule_e:
  year (int), property_addresses: [str], net_rental_income (float)

purchase_contract:
  purchase_price (float), property_address, closing_date (YYYY-MM-DD), buyer_name, seller_name, earnest_money (float)

hoi_declaration:
  insurer_name, property_address, dwelling_coverage (float), annual_premium (float), effective_date (YYYY-MM-DD), expiration_date (YYYY-MM-DD)

voe_written:
  employer_name, employee_name, hire_date (YYYY-MM-DD), employment_status (active|terminated), base_salary (float), pay_frequency, position_title

gift_letter:
  donor_name, donor_relationship, gift_amount (float), property_address, is_repayment_required (bool)

credit_report:
  bureau, report_date (YYYY-MM-DD), borrower_name,
  scores: [{bureau: str, score: int}],
  total_monthly_payments (float), derogatory_count (int)

form_4506c:
  taxpayer_name, ssn_last4, tax_years: [int], signed (bool)

government_id:
  id_type (drivers_license|passport|state_id), name, expiration_date (YYYY-MM-DD), state_or_country

For all other types: extract the most important 3-5 fields you can identify (names, dates, amounts, entities).

QUALITY ISSUES (include relevant ones in the array):
"truncated_or_incomplete", "low_quality_or_blurry", "expired_document", "redacted_critical_fields", "multiple_documents_combined", "wrong_orientation"
"""


def build_classification_message(text: str, filename: str) -> str:
    """Build the user message for text-based documents."""
    return f"""Filename: {filename}

Document text (first 6000 chars):
{text[:6000]}

Classify this mortgage document and extract key data."""


def build_extraction_message(text: str, filename: str, document_type: str) -> str:
    """Build the user message for extraction-only (type already known)."""
    return f"""This document has already been identified as: {document_type}
Filename: {filename}

Document text (first 6000 chars):
{text[:6000]}

Extract the relevant fields for a "{document_type}" document. Set document_type to "{document_type}" in your response."""


def build_vision_message(filename: str) -> str:
    """Build the user message for image-based documents."""
    return f"Classify this mortgage document image. Filename: {filename}. Extract all key fields you can see."


def build_vision_content(filename: str, image_b64: str, mime_type: str = "image/jpeg") -> list[dict]:
    """Build Anthropic-format vision message content."""
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": image_b64,
            },
        },
        {
            "type": "text",
            "text": build_vision_message(filename),
        },
    ]
