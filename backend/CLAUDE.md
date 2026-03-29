# CLAUDE.md — mortgage-intelligence backend

> Read this before writing, editing, or reviewing any backend code in this project.

---

## What This Is

Backend for **mortgage-intelligence** — an AI-agentic mortgage processing platform that eliminates the Processor role for conventional loans (Fannie Mae / Freddie Mac).

**Stack:**
- Framework: FastAPI (async)
- Agent framework: LangGraph + LangChain
- LLM: Ollama (default, open-source) — pluggable to any provider
- Database: PostgreSQL 16 (async via asyncpg)
- Cache: Redis 7
- Storage: MinIO (S3-compatible, open-source)
- Auth: Azure AD (optional) + JWT (default)
- Observability: Langfuse (self-hosted)
- Package manager: uv

---

## Structure

```
backend/
├── main.py                  # FastAPI app factory (create_app pattern)
├── dependencies.py          # Auth + RBAC dependency injection
├── core/
│   └── config.py            # get_settings() — pydantic-settings singleton
├── auth/
│   └── azure_ad.py          # Azure AD OAuth2 (optional)
├── routers/
│   ├── health.py            # Health check
│   ├── auth.py              # Register, login, JWT management
│   ├── loans.py             # Loan CRUD + persona classification + checklist
│   ├── documents.py         # Document upload + classification trigger
│   ├── dashboard.py         # UW pipeline, loan review, SSE streams
│   └── webhooks.py          # Encompass webhook receiver (HMAC verified)
├── agents/                  # All agents extend BaseAgent (auto Langfuse tracing)
│   ├── base_agent.py        # Abstract base with @_traced decorator
│   ├── orchestrator/        # Supervisor agent — routes events
│   ├── document_classifier/ # OCR + classify + extract (25+ doc types)
│   ├── income_calculator/   # FNMA income rules per persona
│   │   └── personas/        # w2, self_employed, commission, retired, rental
│   ├── asset_verifier/      # Bank stmts, large deposits, gift funds
│   ├── employment_verifier/ # VOE, gap detection, verbal VOE
│   ├── credit_analyzer/     # Tri-merge, liability reconciliation
│   ├── compliance_qc/       # TRID, AUS conditions, pre-submission QC
│   ├── uw_package_builder/  # Assemble UW submission package
│   └── tools/               # Shared tool functions for agents
├── services/
│   ├── encompass/
│   │   └── client.py        # Encompass API (OAuth2, rate limit, retry, HMAC)
│   └── rules/               # Deterministic business rules (NO LLM here)
│       ├── doc_requirements/ # Persona → document checklist mapping
│       └── fnma_income/     # FNMA B3-3.1-B3-3.5 income calculation
├── shared/
│   ├── types.py             # All enums (personas, statuses, doc types, confidence)
│   ├── llm.py               # Pluggable LLM provider (Ollama/vLLM/OpenAI/Claude)
│   └── storage.py           # Pluggable storage (MinIO/S3/GCS/Azure/Local)
├── events/
│   └── sse.py               # Server-Sent Events for real-time dashboard
├── db/
│   ├── postgres.py          # get_db() — async session dependency
│   ├── models/              # SQLAlchemy models (9 tables, all with tenant_id)
│   └── migrations/          # Alembic async migrations
├── models/                  # Pydantic request/response schemas (future)
└── tests/
    ├── unit/                # pytest unit tests
    └── evals/               # DeepEval LLM evaluation tests
```

---

## Conventions

- All functions must be `async def`
- Use `get_settings()` (cached) everywhere — never read env vars directly
- All new agents must extend `BaseAgent` — Langfuse tracing is automatic
- **LLMs extract data, Python rules calculate** — never use LLMs for financial math
- All DB models include `tenant_id` for future multi-tenancy
- Every agent decision must include a confidence score (0.0-1.0)
- Format with `ruff format`, lint with `ruff check` (100 char line length)
- Use relative imports within backend (e.g., `from ..core.config import get_settings`)

---

## Running

```bash
uv sync
uv run uvicorn main:app --reload
uv run pytest
uv run ruff format .
uv run ruff check .
```
