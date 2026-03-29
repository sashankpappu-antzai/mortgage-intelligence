# Mortgage Processor

AI-powered mortgage processing platform that automates the Processor role for conventional loans (Fannie Mae / Freddie Mac). Loan Officers and Borrowers upload documents directly, AI agents validate everything, and Underwriters receive a fully verified package with confidence scores and audit trails.

## The Problem

In conventional mortgage lending, the **Processor** sits between the Loan Officer/Borrower and the Underwriter, performing 42+ manual actions across 7 phases:

- Reviewing 1003/URLA applications and classifying borrower profiles
- Chasing borrowers for 25+ document types based on employment persona
- Calculating income per FNMA Selling Guide (B3-3.1 through B3-3.5)
- Cross-validating data across W-2s, tax returns, pay stubs, bank statements, VOEs
- Ordering and tracking third-party services (appraisal, title, flood, HOI, PMI)
- Managing AUS conditions (PTD/PTF/PTC) and linking documents
- Assembling the complete UW submission package

This manual process adds days to every loan, introduces human error, and creates friction between all parties.

## The Solution

An **AI-agentic system** with 9 specialized agents that replaces the Processor role entirely:

```
LO / Borrower  ──uploads──>  AI Agents  ──validated package──>  Underwriter
                              (9 agents)
                              - Classify docs
                              - Calculate income (FNMA rules)
                              - Verify assets & employment
                              - Analyze credit
                              - Track conditions
                              - Cross-validate everything
                              - Build UW package
```

The Underwriter sees a single-view dashboard showing every validation, which agent performed it, the confidence score, source documents, and FNMA guideline citations.

## Architecture

### Four-Layer Design

```
Layer 1: Frontend          Next.js 15 (LO Portal, Borrower Portal, UW Dashboard)
Layer 2: API               FastAPI (REST + WebSocket/SSE for real-time updates)
Layer 3: AI Agents         LangGraph (9 specialist agents with Claude API)
Layer 4: Infrastructure    PostgreSQL, Redis, Cloud Storage, Encompass API
```

### AI Agent Architecture

| Agent | What It Does |
|-------|-------------|
| **Orchestrator** | Routes events to correct specialist agent, manages loan state machine |
| **Document Classifier** | OCR + classify 25+ doc types + extract structured data + route to eFolder |
| **Income Calculator** | Calculate qualifying income per FNMA B3-3.1-B3-3.5 (5 persona paths) |
| **Asset Verifier** | Bank statement analysis, large deposit detection, gift fund validation |
| **Employment Verifier** | VOE ordering/parsing, employment gap detection, verbal VOE scheduling |
| **Credit Analyzer** | Tri-merge parsing, liability reconciliation, undisclosed debt detection |
| **Third-Party Orders** | Appraisal/title/flood/HOI/PMI ordering and tracking via Encompass |
| **Compliance & QC** | TRID timing, AUS condition completeness, pre-submission QC scorecard |
| **UW Package Builder** | Assemble complete submission package with validation citations |

**Key design principle**: LLMs extract data from documents; deterministic Python rules engines perform all financial calculations. Claude reads a W-2 and extracts box values, but codified FNMA rules do the income math. This prevents hallucination on financial calculations.

### Confidence Scoring

Every agent decision carries a confidence score:
- **HIGH (0.90-1.0)** - Auto-validated, no human review needed
- **MEDIUM (0.70-0.89)** - Validated but flagged for UW awareness
- **LOW (0.50-0.69)** - Requires LO clarification before proceeding
- **ESCALATE (<0.50)** - Cannot determine; routed to human review queue

### Borrower Personas

The system classifies borrowers into personas from 1003 data, each with different document requirements:

| Persona | Key Documents | FNMA Reference |
|---------|--------------|----------------|
| **W-2 Salaried** | W-2s (2yr), pay stubs (30d), VOE | B3-3.1-01 |
| **Self-Employed** | Personal + business tax returns (2yr), YTD P&L, K-1s | B3-3.2-01 |
| **Commission/Variable** | W-2s (2yr), tax returns (2yr avg), written VOE with breakdown | B3-3.1-09 |
| **Retired/Fixed** | SS award letter, pension statements, 1099-R | B3-3.1-09 |
| **Rental Income** | Schedule E (2yr), lease agreements, mortgage statements | B3-3.1-08 |

Plus universal documents required for all borrowers (bank statements, credit report, photo ID, 4506-C, etc.).

## 100% Open-Source Stack

Every component is open-source and self-hostable. **No proprietary API dependencies.** The system runs entirely on your infrastructure with no external service calls required.

| Component | Technology | License | Notes |
|-----------|-----------|---------|-------|
| Backend | **Python 3.12 + FastAPI** | MIT | Web framework + API |
| Frontend | **Next.js 15 + TypeScript + Tailwind** | MIT | React Server Components |
| AI Agents | **LangGraph 1.0** | MIT | Stateful multi-step agent workflows |
| LLM (default) | **Ollama** (local models) | MIT | Llama 3.1, Mistral, LLaVA for vision. No API key needed |
| LLM (alt) | **vLLM / LiteLLM** | Apache 2.0 / MIT | High-throughput self-hosted inference |
| Workflow Engine | **Temporal** | MIT | Durable execution for 30-45 day loan lifecycles |
| Database | **PostgreSQL 16** | PostgreSQL License | Row-Level Security for multi-tenancy |
| Cache/Realtime | **Redis 7** | BSD | Pub/sub for SSE dashboard updates |
| Object Storage | **MinIO** (S3-compatible) | AGPL-3.0 | Self-hosted document storage. Also works with any S3/GCS/Azure |
| Observability | **Langfuse** (self-hosted) | MIT | Agent decision tracing for compliance audit |
| LOS Integration | **Encompass API v3** | N/A | Customer's system of record (not our dependency) |

### LLM Provider is Pluggable

The system defaults to **Ollama** (fully local, no API key). You can swap to any provider without code changes:

```bash
# Default: Ollama (local, open-source)
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
LLM_DEFAULT_MODEL=llama3.1

# Alternative: vLLM (self-hosted, open-source)
LLM_PROVIDER=vllm
LLM_BASE_URL=http://localhost:8080

# Alternative: LiteLLM proxy (open-source, routes to any backend)
LLM_PROVIDER=litellm
LLM_BASE_URL=http://localhost:4000

# Optional: Cloud APIs (if you choose to use them)
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
```

## Repository Structure

```
mortgage-processor/
  apps/
    api/                          # FastAPI backend
      app/
        main.py                   # App entry point
        config.py                 # Pydantic settings (env-based)
        dependencies.py           # Auth + RBAC dependency injection
        routers/
          auth.py                 # Register, login, JWT management
          loans.py                # Loan CRUD + persona classification
          documents.py            # Document upload + classification trigger
          dashboard.py            # UW pipeline + loan review + SSE streams
          webhooks.py             # Encompass webhook receiver (HMAC verified)
        events/
          sse.py                  # Server-Sent Events for real-time updates
    web/                          # Next.js 15 frontend
      src/
        app/
          (auth)/                 # Login, Register pages
          (dashboard)/            # LO portal
            loans/                # Loan list, loan detail, new loan form
            pipeline/             # UW pipeline view
          (uw)/                   # UW review dashboard (Milestone 6)
          (borrower)/             # Borrower portal (Milestone 7)
        lib/
          api.ts                  # Typed API client
          auth.ts                 # Zustand auth store
          utils.ts                # Formatting helpers
    workers/                      # Temporal workflow workers
      workflows/                  # loan_lifecycle, doc_processing, income_calc
      activities/                 # encompass, agents, notifications
  packages/
    agents/                       # LangGraph agent definitions
      orchestrator/               # Supervisor agent (routes events)
      document_classifier/        # OCR + classify + extract
      income_calculator/          # FNMA income rules
        personas/                 # w2, self_employed, commission, retired, rental
      asset_verifier/             # Bank stmt + gift fund validation
      employment_verifier/        # VOE + gap detection
      credit_analyzer/            # Tri-merge + liability reconciliation
      compliance_qc/              # TRID + AUS + pre-submission QC
      uw_package_builder/         # Assemble UW submission package
    encompass_client/             # Encompass API abstraction
      client.py                   # OAuth2, rate limiting, retry, HMAC webhooks
    db/                           # Database layer
      models/                     # SQLAlchemy models (8 core tables)
      migrations/                 # Alembic async migrations
      repositories/               # Data access patterns
    rules/                        # Deterministic business rules
      fnma_income/                # Income calculation per FNMA Selling Guide
      compliance/                 # TRID, HMDA, QM/ATR
      doc_requirements/           # Persona-to-document checklist mapping
    shared/                       # Cross-cutting concerns
      types.py                    # Enums (personas, statuses, doc types, etc.)
      storage.py                  # Cloud-agnostic storage (S3/GCS/Azure/Local)
  infrastructure/
    docker/
      docker-compose.prod.yml     # Production deployment (configurable replicas)
    terraform/
      main.tf                     # Cloud-provider switchable (aws/gcp/azure)
      variables.tf                # All infra params configurable
      modules/aws/                # VPC, RDS, ElastiCache, ECS Fargate, S3
  docker-compose.yml              # Local dev (Postgres + Redis)
  pyproject.toml                  # Python dependencies
  Makefile                        # Dev commands (dev, test, lint, migrate)
  .env.example                    # All config variables documented
```

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- [Ollama](https://ollama.ai) (for local AI models - optional but recommended)

### Quick Start (Everything Self-Hosted)

```bash
# Clone
git clone git@github.com:sashankpappu-antzai/mortgage-processor.git
cd mortgage-processor

# Copy environment config (defaults work out of the box)
cp .env.example .env

# Start all infrastructure (Postgres + Redis + MinIO + Langfuse)
docker compose up -d

# Install Ollama and pull models (for AI agents)
# Install from https://ollama.ai, then:
ollama pull llama3.1    # Text model
ollama pull llava       # Vision model (document OCR)

# Install Python dependencies
pip install -e ".[dev]"

# Run database migrations
make db-migrate

# Install frontend dependencies
cd apps/web && npm install && cd ../..

# Start API server (port 8000)
make dev-api

# Start frontend (port 3000) - in another terminal
make dev-web
```

### What's Running

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:8000 | FastAPI backend + Swagger docs at /docs |
| Frontend | http://localhost:3000 | Next.js web application |
| MinIO Console | http://localhost:9001 | Document storage admin (minioadmin/minioadmin) |
| Langfuse | http://localhost:3001 | Agent observability dashboard |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache + pub/sub |
| Ollama | localhost:11434 | Local LLM inference |

### Production Deployment

```bash
# Using Docker Compose
cd infrastructure/docker
docker compose -f docker-compose.prod.yml up -d

# Using Terraform (AWS)
cd infrastructure/terraform
terraform init
terraform plan -var="environment=production" -var="cloud_provider=aws"
terraform apply
```

## Configuration

All configuration is via environment variables (see `.env.example`). Defaults work out of the box with `docker compose up`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | localhost PostgreSQL | PostgreSQL connection string |
| `REDIS_URL` | localhost Redis | Redis connection string |
| `STORAGE_PROVIDER` | `s3` | `s3` (MinIO), `gcs`, `azure`, or `local` |
| `STORAGE_ENDPOINT_URL` | `http://localhost:9000` | MinIO/S3 endpoint |
| `LLM_PROVIDER` | `ollama` | `ollama`, `vllm`, `litellm`, `openai`, `anthropic` |
| `LLM_BASE_URL` | `http://localhost:11434` | LLM server URL |
| `LLM_DEFAULT_MODEL` | `llama3.1` | Default text model |
| `LLM_VISION_MODEL` | `llava` | Vision model for document OCR |
| `LANGFUSE_HOST` | `http://localhost:3001` | Langfuse observability UI |
| `ENCOMPASS_INSTANCE_URL` | (empty) | Encompass API (only when connecting to live LOS) |
| `JWT_SECRET_KEY` | dev default | Change in production |

## Encompass Integration

The system uses Encompass as the **system of record**. Our platform is an AI layer that reads from and writes to Encompass via API.

**Inbound (webhooks):**
- `loan.milestone.changed` - Triggers phase transitions
- `loan.document.added` - Triggers Document Classifier Agent
- `loan.condition.statusChanged` - Updates condition tracking
- `loan.field.changed` - Triggers selective re-validation

**Outbound (API writes):**
- eFolder document uploads and categorization
- Condition status updates (Open -> Received -> Cleared)
- Milestone advancement
- Loan field updates (income, DTI, LTV calculations)

All webhooks verified via HMAC-SHA256 signature. OAuth2 tokens auto-refreshed. Rate limiting and retry logic built into the client.

## Milestone Roadmap

| # | Milestone | Status | What It Delivers |
|---|-----------|--------|-----------------|
| 1 | Foundation + Loan Intake | **Done** | Persona classification, dynamic checklist, Encompass webhooks |
| 2 | Document Intelligence | Next | OCR + classify 25+ doc types + extract data + link to conditions |
| 3 | Income Calculation | Planned | FNMA income calc for 5 persona paths + DTI + worksheets |
| 4 | Asset & Employment | Planned | Bank stmt verification, VOE, gap detection, auto-LOE |
| 5 | Credit + Third-Party | Planned | Credit analysis, appraisal/title/flood ordering, fee validation |
| 6 | UW Dashboard + QC | Planned | Single-view dashboard, validation matrix, QC scorecard |
| 7 | Closing + Borrower Portal | Planned | CD prep, borrower self-service, end-to-end lifecycle |
| 8 | Production Hardening | Planned | Multi-tenant, load testing, security audit, SOC 2 |

## Contributing

### Development Workflow

1. Pick a milestone or issue to work on
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make changes following the patterns in existing code
4. Run linting: `make lint`
5. Run tests: `make test`
6. Submit a PR with a description of what changed and why

### Code Conventions

**Backend (Python):**
- FastAPI routers in `apps/api/app/routers/`
- Business rules (deterministic) in `packages/rules/` - never use LLMs for financial calculations
- AI agents in `packages/agents/` using LangGraph
- All database models include `tenant_id` for future multi-tenancy
- Pydantic models for all request/response schemas

**Frontend (TypeScript):**
- Next.js App Router with route groups: `(auth)`, `(dashboard)`, `(uw)`, `(borrower)`
- API calls through `src/lib/api.ts` (typed client)
- Tailwind CSS with custom theme variables in `globals.css`
- Role-based navigation (LO sees loans, UW sees pipeline)

**Agents:**
- Each agent is a LangGraph graph in its own package under `packages/agents/`
- LLMs extract data, Python rules calculate - never the other way around
- Every agent decision must include a confidence score
- All agent actions logged to `audit_events` table

**Infrastructure:**
- Storage is cloud-agnostic (S3/GCS/Azure/Local) via `packages/shared/storage.py`
- All config via environment variables (see `.env.example`)
- Docker containers for all services
- Terraform for cloud provisioning (switchable between AWS/GCP/Azure)

### Key Files to Understand First

| File | Purpose |
|------|---------|
| `packages/shared/types.py` | All enums - personas, statuses, doc types, confidence levels |
| `packages/rules/doc_requirements/checklists.py` | Persona classifier + document checklist generator |
| `packages/encompass_client/client.py` | Encompass API client (all LOS interactions) |
| `packages/db/models/loan.py` | Core data model (Loan + LoanBorrower) |
| `apps/api/app/routers/loans.py` | Loan CRUD with persona classification |
| `apps/api/app/routers/webhooks.py` | Encompass event processing |
| `apps/web/src/lib/api.ts` | Frontend API client (typed) |

## Mortgage Domain Context

### Loan Processing Phases (What We Automate)

| Phase | What Happens | Our Agent |
|-------|-------------|-----------|
| 0. Intake | Review 1003, classify borrower, generate doc checklist | Orchestrator |
| 1. AUS & Credit | Pull credit, submit to DU/LP, parse conditions | Credit Analyzer |
| 2. Doc Collection | Collect, classify, OCR, index documents | Document Classifier |
| 3. Verification | Calculate income, verify assets/employment, cross-validate | Income Calc + Asset + Employment |
| 4. Third Party | Order appraisal, title, flood, HOI, PMI | Third-Party Orders |
| 5. UW Submission | Pre-submission QC, submit to UW, clear conditions | Compliance QC + UW Package Builder |
| 6. Closing | CD prep, final VOE, credit refresh, closing package | Orchestrator |

### Key Acronyms

| Acronym | Meaning |
|---------|---------|
| LO | Loan Officer |
| UW | Underwriter |
| AUS | Automated Underwriting System |
| DU | Desktop Underwriter (Fannie Mae) |
| LP | Loan Product Advisor (Freddie Mac) |
| FNMA | Federal National Mortgage Association (Fannie Mae) |
| PTD | Prior to Document (condition type) |
| PTF | Prior to Funding |
| PTC | Prior to Closing |
| CTC | Clear to Close |
| DTI | Debt-to-Income ratio |
| LTV | Loan-to-Value ratio |
| VOE | Verification of Employment |
| HOI | Homeowners Insurance |
| PMI | Private Mortgage Insurance |
| TRID | TILA-RESPA Integrated Disclosure |
| LOE | Letter of Explanation |
| 1003/URLA | Uniform Residential Loan Application |

## Open-Source Commitment

This project is built entirely on open-source technologies. Every dependency is self-hostable. No vendor lock-in.

| Layer | Open-Source Choice | Proprietary Alternative (optional) |
|-------|-------------------|-----------------------------------|
| LLM | Ollama + Llama 3.1 | OpenAI, Anthropic (via config) |
| Object Storage | MinIO | AWS S3, GCS, Azure Blob (via config) |
| Observability | Langfuse | LangSmith, Datadog (via config) |
| Database | PostgreSQL | None needed |
| Cache | Redis | None needed |
| Search | PostgreSQL FTS + pgvector | Elasticsearch (future) |

## License

MIT License. See [LICENSE](LICENSE) for details.
