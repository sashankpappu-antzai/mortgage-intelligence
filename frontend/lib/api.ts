const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type FetchOptions = RequestInit & { token?: string };

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

  const res = await fetch(`${API_BASE}${path}`, { ...fetchOptions, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `API error: ${res.status}`);
  }

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

export async function uploadDocument(loanId: string, file: File, documentType?: string): Promise<unknown> {
  const formData = new FormData();
  formData.append("file", file);
  if (documentType) formData.append("document_type", documentType);

  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const res = await fetch(`${API_BASE}/api/loans/${loanId}/documents`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
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
