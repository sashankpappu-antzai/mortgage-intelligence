const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type FetchOptions = RequestInit & { token?: string };

// Deduplicate concurrent refresh calls — only one in-flight at a time
let _refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    const refreshToken = typeof window !== "undefined" ? localStorage.getItem("refresh_token") : null;
    if (!refreshToken) return null;

    try {
      const res = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!res.ok) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user");
        return null;
      }

      const data = await res.json();
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      localStorage.setItem("user", JSON.stringify(data.user));
      return data.access_token as string;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { token, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  } else if (typeof window !== "undefined") {
    const stored = localStorage.getItem("access_token");
    if (stored) headers["Authorization"] = `Bearer ${stored}`;
  }

  let res = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers });

  // On 401, attempt silent token refresh and retry once
  if (res.status === 401 && !token) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers });
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `API error: ${res.status}`);
  }

  // 204 No Content — nothing to parse
  if (res.status === 204) return undefined as T;

  return res.json();
}

// --- Auth ---

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: { id: string; email: string; name: string; role: string };
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(data: {
  email: string;
  password: string;
  name: string;
  role?: string;
  tenant_name?: string;
}): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getMe() {
  return apiFetch<{ id: string; email: string; name: string; role: string; tenant_id: string }>("/api/auth/me");
}

// --- Microsoft / Azure AD ---

export interface MicrosoftConfig {
  configured: boolean;
  tenant_id?: string;
  client_id?: string;
  redirect_uri?: string;
}

export interface MicrosoftLoginResponse {
  needs_role?: boolean;
  email?: string;
  name?: string;
  azure_ad_oid?: string;
  access_token?: string;
  refresh_token?: string;
  token_type?: string;
  user?: { id: string; email: string; name: string; role: string };
}

export async function getMicrosoftConfig(): Promise<MicrosoftConfig> {
  return apiFetch<MicrosoftConfig>("/api/auth/microsoft/config");
}

export async function microsoftLogin(code: string, redirectUri: string): Promise<MicrosoftLoginResponse> {
  return apiFetch<MicrosoftLoginResponse>("/api/auth/microsoft", {
    method: "POST",
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });
}

export async function microsoftComplete(data: {
  code: string;
  redirect_uri: string;
  role: string;
  tenant_name: string;
}): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/api/auth/microsoft/complete", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// --- Loans ---

export interface LoanSummary {
  id: string;
  encompass_loan_number: string | null;
  status: string;
  processing_phase: string;
  primary_borrower_persona: string | null;
  borrower_name: string | null;
  loan_amount: number | null;
  loan_purpose: string | null;
  ai_readiness_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface LoanDetail extends LoanSummary {
  encompass_loan_id: string | null;
  occupancy_type: string | null;
  property_type: string | null;
  purchase_price: number | null;
  appraised_value: number | null;
  interest_rate: number | null;
  loan_term_months: number | null;
  ltv: number | null;
  cltv: number | null;
  dti_front: number | null;
  dti_back: number | null;
  qualifying_income_monthly: number | null;
  aus_type: string | null;
  aus_finding: string | null;
  credit_score_borrower: number | null;
  representative_credit_score: number | null;
  encompass_milestone: string | null;
  borrowers: Array<{
    id: string;
    first_name: string;
    last_name: string;
    borrower_type: string;
    persona: string | null;
    employment_type: string | null;
    self_employed: boolean | null;
  }>;
  document_checklist: ChecklistItem[];
  conditions_summary: { open: number; received: number; cleared: number; total: number };
}

export interface ChecklistItem {
  document_type: string;
  category: string;
  label: string;
  required: boolean;
  status: string;
  description: string | null;
}

export async function listLoans(params?: { status?: string }): Promise<LoanSummary[]> {
  const query = params?.status ? `?status=${params.status}` : "";
  return apiFetch<LoanSummary[]>(`/api/loans${query}`);
}

export async function getLoan(loanId: string): Promise<LoanDetail> {
  return apiFetch<LoanDetail>(`/api/loans/${loanId}`);
}

export async function createLoan(data: {
  loan_purpose: string;
  loan_amount?: number;
  purchase_price?: number;
  occupancy_type?: string;
  property_type?: string;
  borrowers: Array<{
    first_name: string;
    last_name: string;
    email?: string;
    borrower_type?: string;
    employment_type?: string;
    self_employed?: boolean;
    ownership_percentage?: number;
    income_sources?: Record<string, number>;
  }>;
}): Promise<LoanDetail> {
  return apiFetch<LoanDetail>("/api/loans", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// --- Documents ---

export interface DocumentItem {
  id: string;
  loan_id: string;
  document_type: string | null;
  category: string | null;
  title: string | null;
  file_name: string;
  status: string;
  classification_confidence: number | null;
  extracted_data: Record<string, unknown> | null;
  page_count: number | null;
  created_at: string;
}

// --- Validations ---

export interface ValidationResult {
  id: string;
  agent_name: string;
  validation_type: string;
  confidence_score: number;
  confidence_level: string;
  status: string;
  flags: Record<string, unknown> | null;
  result: {
    identity?: Record<string, unknown>;
    employer?: Record<string, unknown>;
    income?: Record<string, unknown>;
    completeness?: {
      documents?: Array<{
        doc_id: string;
        document_type: string;
        file_name: string;
        complete: boolean;
        deficiencies: Array<{
          field: string;
          severity: string;
          message: string;
          action_required: string;
        }>;
        stale?: boolean;
        stale_reason?: string;
        missing_pages?: boolean;
        missing_signature?: boolean;
      }>;
      total_deficiencies?: number;
      critical_count?: number;
      confidence?: number;
      flags?: string[];
      skipped?: boolean;
    };
    gaps?: {
      missing_documents?: Array<{
        document_type: string;
        label: string;
        category: string;
        required: boolean;
        priority: string;
        borrower_message: string;
        processor_note?: string;
      }>;
      re_upload_needed?: Array<{
        document_type: string;
        doc_id: string;
        file_name: string;
        reason: string;
      }>;
      checklist_completion_pct?: number;
      total_required?: number;
      total_received?: number;
      total_missing?: number;
      needs_list_summary?: string;
      confidence?: number;
      flags?: string[];
      skipped?: boolean;
    };
    aggregate?: {
      overall_pass?: boolean;
      overall_confidence?: number;
      identity_pass?: boolean;
      employer_pass?: boolean;
      income_pass?: boolean;
      completeness_pass?: boolean;
      checklist_pass?: boolean;
      critical_flags?: string[];
      warnings?: string[];
      borrower_action_items?: string[];
      recommendation?: string;
      summary?: string;
    };
  };
  processing_time_ms: number | null;
  created_at: string;
}

export async function listValidations(loanId: string): Promise<ValidationResult[]> {
  return apiFetch<ValidationResult[]>(`/api/loans/${loanId}/validations`);
}

export async function triggerValidation(loanId: string): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/loans/${loanId}/validate`, { method: "POST" });
}

export async function deleteLoan(loanId: string): Promise<void> {
  await apiFetch(`/api/loans/${loanId}`, { method: "DELETE" });
}

export async function deleteBorrower(loanId: string, borrowerId: string): Promise<void> {
  await apiFetch(`/api/loans/${loanId}/borrowers/${borrowerId}`, { method: "DELETE" });
}

export async function listDocuments(loanId: string): Promise<DocumentItem[]> {
  const res = await apiFetch<{ documents: DocumentItem[]; total: number }>(`/api/loans/${loanId}/documents`);
  return res.documents;
}

export async function uploadDocument(loanId: string, file: File, documentType?: string): Promise<unknown> {
  const formData = new FormData();
  formData.append("file", file);
  const url = `${API_BASE}/api/loans/${loanId}/documents${documentType ? `?document_type=${encodeURIComponent(documentType)}` : ""}`;

  async function doUpload(token: string | null) {
    return fetch(url, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
  }

  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  let res = await doUpload(token);

  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) res = await doUpload(newToken);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function getDocumentFileBlob(loanId: string, documentId: string): Promise<Blob> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const res = await fetch(`${API_BASE}/api/loans/${loanId}/documents/${documentId}/file`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      const retry = await fetch(`${API_BASE}/api/loans/${loanId}/documents/${documentId}/file`, {
        headers: { Authorization: `Bearer ${newToken}` },
      });
      if (!retry.ok) throw new Error("Failed to load document file");
      return retry.blob();
    }
  }
  if (!res.ok) throw new Error("Failed to load document file");
  return res.blob();
}

export async function confirmDocument(
  loanId: string,
  documentId: string,
  updates: { document_type?: string; status?: string }
): Promise<DocumentItem> {
  return apiFetch<DocumentItem>(`/api/loans/${loanId}/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

export async function deleteDocument(loanId: string, documentId: string): Promise<void> {
  await apiFetch(`/api/loans/${loanId}/documents/${documentId}`, { method: "DELETE" });
}

// --- Dashboard ---

export interface PipelineItem {
  loan_id: string;
  encompass_loan_number: string | null;
  borrower_name: string | null;
  loan_officer_name: string | null;
  loan_amount: number | null;
  status: string;
  processing_phase: string;
  ai_readiness_score: number | null;
  primary_borrower_persona: string | null;
  conditions_open: number;
  conditions_total: number;
  documents_uploaded: number;
  documents_validated: number;
  credit_score: number | null;
  dti_back: number | null;
  ltv: number | null;
  updated_at: string;
}

export async function getPipeline(params?: { status?: string }): Promise<PipelineItem[]> {
  const query = params?.status ? `?status=${params.status}` : "";
  return apiFetch<PipelineItem[]>(`/api/dashboard/pipeline${query}`);
}

// --- SSE ---

export function subscribeLoanEvents(loanId: string, onMessage: (data: unknown) => void): () => void {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  // EventSource doesn't support custom headers - pass token as query param
  const url = `${API_BASE}/api/dashboard/events/loan/${loanId}${token ? `?token=${token}` : ""}`;
  const es = new EventSource(url);
  es.onmessage = (event) => onMessage(JSON.parse(event.data));
  es.onerror = () => {
    // Auto-reconnect is built into EventSource, but log for debugging
    console.warn("SSE connection error, will auto-reconnect");
  };
  return () => es.close();
}

export function subscribePipelineEvents(onMessage: (data: unknown) => void): () => void {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const url = `${API_BASE}/api/dashboard/events/pipeline${token ? `?token=${token}` : ""}`;
  const es = new EventSource(url);
  es.onmessage = (event) => onMessage(JSON.parse(event.data));
  return () => es.close();
}
