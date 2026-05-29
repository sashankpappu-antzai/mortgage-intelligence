# Enterprise Adoption Review — `mortgage-intelligence`

Consolidated architecture + security review for enterprise adoption as a productised, customer-deployed offering.

Severity scale:
- **CRITICAL** — tenant compromise / GLBA breach / production-stoppable
- **HIGH** — enterprise-blocking
- **MEDIUM** — GA-blocking
- **LOW** — post-GA cleanup

---

## Verdict

> **Not adoptable for production NPI/GLBA workload in current state.** At least seven independently-sufficient tenant-compromise paths exist (default JWT secret, unsigned Azure ID-token, unauthenticated SSE, open self-elected admin registration, fail-open webhook HMAC, JWT-in-localStorage + wildcard CORS, MinIO/Postgres default creds with exposed host ports). The architecture has the right ingredients (multi-tenant schema, agent abstraction, Langfuse hooks, deterministic-rules separation) but the implementation is at "internal demo" maturity, not enterprise. A focused 6–10 week hardening sprint can get it to pilot; SOC 2 / GLBA readiness is a quarter beyond that.

## Top 12 to fix before any pilot with real borrower data

1. Rotate the leaked Anthropic key (in `infra/.env`), and any other secret co-located in that file. Move secrets to a vault.
2. Fail-fast startup if `JWT_SECRET_KEY` matches the default or is <32 random bytes; switch to RS256/EdDSA with `aud`/`iss`/`jti`/`typ`. (`backend/core/config.py:23`)
3. Verify Azure AD `id_token` against tenant JWKS + add OAuth `state`+PKCE+`nonce`. (`backend/auth/azure_ad.py:34-47`)
4. Lock `/auth/register` to invite-only; server-assigns `role` and `tenant`; add password policy + rate limit. (`backend/routers/auth.py:59-90`)
5. Tenant-scope SSE + drop query-string token; channel-namespace by tenant; sanitize SSE payloads (no PII). (`backend/events/sse.py:15-53`, `backend/routers/dashboard.py:245-262`, `frontend/lib/api.ts:454`)
6. Fail-closed webhook HMAC + timestamp/replay window + resolve tenant from `instance_id`. (`backend/services/encompass/client.py:222-234`, `backend/routers/webhooks.py:64,162`)
7. File-upload hardening: size cap, magic-byte sniff, MIME allow-list, sanitized stored filename, force `Content-Disposition: attachment` for non-PDF/image. (`backend/routers/documents.py:85-214`)
8. Move JWTs from `localStorage` → `HttpOnly; Secure; SameSite=Strict` cookies; add CSP; add CSRF token on mutating routes. (`frontend/lib/auth.ts:27-30`)
9. Wire `require_role(...)` onto every router; restrict dashboard/pipeline + delete endpoints to UW/ADMIN. (`backend/dependencies.py:44-55`)
10. Replace `fastapi.BackgroundTasks` with Arq/Celery/Temporal for classification + validation. (`backend/routers/documents.py:156`, `backend/routers/loans.py:296-314`)
11. Fix the classifier "silent success" bug — pre-typed extraction failure must not leave `status=CLASSIFIED` with empty `extracted_data`. (`backend/agents/document_classifier/agent.py:313-318`)
12. Turn off `echo=True`; switch to structured JSON logs; add `X-Request-Id` correlation. (`backend/db/postgres.py:12`, `backend/main.py`)

---

# Detailed Checklist

## 1. Secrets & Configuration

- **[CRITICAL]** Live Anthropic key (`sk-ant-…`) checked into developer-shared `infra/.env`. Gitignored, but present in every clone, backup, and `tar` archive. Rotate immediately; move to vault (SSM/Vault/Doppler). Add `gitleaks`/`trufflehog` pre-commit. (`infra/.env:51`)
- **[CRITICAL]** `JWT_SECRET_KEY` defaults to `"dev-secret-change-in-production"` in code AND env file. Refuse startup when value matches default and `app_env != "dev"`. (`backend/core/config.py:23`, `infra/.env:16`)
- **[HIGH]** MinIO default credentials `minioadmin/minioadmin`. (`infra/docker-compose.yml:68-69`)
- **[HIGH]** Postgres exposed at host `0.0.0.0:5432` with `postgres/postgres`. Bind to `127.0.0.1:` only in dev; remove host port in prod. (`infra/docker-compose.yml:41-44`)
- **[HIGH]** Langfuse runs with `NEXTAUTH_SECRET=langfuse-dev-secret` + default salt and is exposed on `:3001` while ingesting PII-bearing telemetry. (`infra/docker-compose.yml:103-105`)
- **[HIGH]** `Tenant.encompass_client_secret_ref` column documented as "reference to vault, never the actual secret" but webhook path uses global `settings.encompass_client_secret`. Complete the vault path or remove the dead column. (`backend/routers/webhooks.py:47`)
- **[MEDIUM]** `AZURE_STORAGE_CONNECTION_STRING` read via `os.environ` directly, bypassing the `get_settings()` discipline. (`backend/shared/storage.py:114`)
- **[MEDIUM]** No SBOM / supply-chain pinning; `uv.lock` not committed; `pyproject.toml` uses `>=` floors throughout.
- **[LOW]** `docker compose restart` does not reload `.env`; must use `--force-recreate`. Document in runbook.

## 2. Authentication & Session

- **[CRITICAL]** JWT HS256 + same static secret for access AND refresh; no `aud`/`iss`/`jti`/`typ`. Refresh tokens accepted as access tokens and vice versa. Switch to RS256/EdDSA from KMS; add claim discrimination; validate `aud`, `iss`. (`backend/routers/auth.py:50-56`, `backend/dependencies.py:21-37`)
- **[CRITICAL]** No refresh-token rotation, no revocation list, no `/logout` endpoint. Stolen refresh token = 7 days of unrevokable session continuity. Add `refresh_tokens` table with `jti, revoked_at, replaced_by_jti`; one-time-use rotation; reuse-detection auto-revokes the chain.
- **[CRITICAL]** Azure AD `id_token` signature is NOT verified — `pyjwt.decode(id_token, options={"verify_signature": False})`. Trusting the unsigned `oid`/`email` against the local user table = forge any user. Fetch tenant JWKS, verify signature + `iss` + `aud=client_id` + `exp` + `nbf`. (`backend/auth/azure_ad.py:34-47`)
- **[CRITICAL]** `/auth/register` lets clients self-elect `role=ADMIN` and join any existing `tenant_name`. Combined with `Tenant.name` not being unique, anyone registers as admin of any tenant. Make registration invite-only; server-assigns role + tenant. (`backend/routers/auth.py:22-90`)
- **[HIGH]** No OAuth `state` / PKCE / `nonce` in Azure AD flow; `redirect_uri` taken verbatim from request body. (`backend/auth/azure_ad.py:15-31`)
- **[HIGH]** Single-use Azure auth `code` exchanged twice (`/microsoft` then `/microsoft/complete`). (`backend/routers/auth.py:181-223`)
- **[HIGH]** No password policy (`password: str` accepts `"a"`). Add ≥12 chars + zxcvbn + HIBP k-anonymity. (`backend/routers/auth.py:22-26`)
- **[HIGH]** No rate limit on `/login`, `/register`, `/refresh`. Add `slowapi` with Redis backend + lockout. (`backend/routers/auth.py`)
- **[HIGH]** `/register` enumerates accounts via `"Email already registered"`. Return uniform 202.
- **[HIGH]** `require_role(...)` is defined but never invoked on any router. Every router relies on inline `if user.role == ...` checks; many routers (dashboard, validate, delete) have no role check at all. Add `Depends(require_role(...))` everywhere. (`backend/dependencies.py:44-55`)
- **[HIGH]** Both `PyJWT` and `python-jose` declared; `python-jose<3.4` has algorithm-confusion + JWT-bomb CVEs (CVE-2024-33663/33664). Standardize on `PyJWT`; remove jose. (`pyproject.toml:16-17`)
- **[HIGH]** `passlib` is unmaintained since 2020; the explicit `bcrypt>=4.0,<4.3` pin exists because passlib breaks with bcrypt 4.1+. Migrate to bcrypt directly or `argon2-cffi`. (`pyproject.toml:18`)
- **[MEDIUM]** No email-verification flag — registered users are immediately active.
- **[MEDIUM]** `Tenant.name` not unique → `/register` with `tenant_name="Default"` collides into the same tenant. Make unique; remove from public surface entirely. (`backend/db/models/tenant.py:14`)

## 3. Authorization, Tenancy, IDOR

- **[CRITICAL]** **SSE has no real auth or tenant scoping.** `EventSource` cannot send Authorization headers, so the backend's `Depends(get_current_user)` is unsatisfiable; the frontend pastes the token into the query string (`?token=…`), which the backend doesn't even read. Either the feature is broken or it's running through a bypass. Independently, `subscribe_loan(loan_id)` does no tenant check, and the global `pipeline` channel broadcasts every tenant's events to every subscriber. SSE payloads include extracted PII (SSN-last-4, wages, employer). Fix: explicit query-param token verification on the SSE route, tenant-scoped channels (`pipeline:{tenant_id}`, `loan:{tenant_id}:{loan_id}`), and payloads stripped of `extracted_data`. (`backend/events/sse.py:15-53`, `backend/routers/dashboard.py:245-262`, `frontend/lib/api.ts:454`)
- **[CRITICAL]** Webhook handler hardcodes `tenant_id=00000000-0000-0000-0000-000000000000`; placeholder loans created with this tenant. Resolve from `Tenant.encompass_instance_id` and reject unmapped. (`backend/routers/webhooks.py:64,162`)
- **[HIGH]** `/api/dashboard/pipeline` exposes every loan in the tenant to any authenticated user including BORROWER role. (`backend/routers/dashboard.py:64-131`)
- **[HIGH]** `DELETE /api/loans/{id}` and `DELETE /…/borrowers/{bid}` allowed for any tenant-member; no role gate; hard-deletes destroy audit evidence. Restrict to ADMIN; soft-delete with audit. (`backend/routers/loans.py:317-366`)
- **[HIGH]** Background tasks load `Document`/`Loan` by id alone — no `tenant_id` filter. A bug or stale task can cross tenants. Add `tenant_id` to every async-task query. (`backend/services/loan_metrics.py:653-659`, `backend/agents/document_classifier/agent.py:255`, `backend/agents/cross_doc_validator/agent.py:45-58`)
- **[HIGH]** Document fetch joins by `(id, loan_id)` (good) but not by `Document.tenant_id`. Defense-in-depth: add the tenant predicate. (`backend/routers/documents.py:172-180`)
- **[HIGH]** Borrower role can upload documents to any loan in tenant (no `borrower_id` ownership check). (`backend/routers/documents.py:85-165`)
- **[MEDIUM]** No PostgreSQL row-level security policies as last-line defense.
- **[MEDIUM]** `PATCH /documents/{id}` lets caller force any status (incl. `VALIDATED`), bypassing the classifier. Restrict transitions; UW/ADMIN only. (`backend/routers/documents.py:223-267`)

## 4. Input / Output Handling

- **[HIGH]** File uploads: no size cap, `await file.read()` slurps the entire body into memory (DoS), no magic-byte check, MIME taken from client. Add `MaxBodySize`, `python-magic`/`filetype` sniff, allow-list `application/pdf|image/png|image/jpeg|image/tiff`. (`backend/routers/documents.py:85-165`)
- **[HIGH]** Documents served `inline` with client-supplied `media_type` — `evil.svg` with `image/svg+xml` renders inline same-origin and steals `localStorage["access_token"]`. Force `attachment` for non-PDF/image; emit `X-Content-Type-Options: nosniff` and a sandbox CSP; RFC 5987-escape the filename in `Content-Disposition`. (`backend/routers/documents.py:207-214`)
- **[HIGH]** Storage path includes raw `file.filename` — `tenants/{tid}/loans/{lid}/documents/{uuid}/{filename}`. On POSIX `..` segments collapse below the intended dir; on Windows `..\..` works. Sanitize via `secure_filename` or replace filename with `{uuid}.{safe_ext}`. (`backend/routers/documents.py:123`, `backend/shared/storage.py:160`)
- **[MEDIUM]** No virus scanning hook before docs are served back to UWs or shipped to Encompass. Wire ClamAV.
- **[MEDIUM]** `Loan.notes` freeform; ensure React doesn't render via `dangerouslySetInnerHTML` (spot-check clean — track).

## 5. Crypto, PII, Data at Rest

- **[HIGH]** PII columns plaintext: `loan_borrowers.{first_name,last_name,email,phone,employer_name}`, `Loan.loan_data` JSONB (Encompass snapshot incl. SSN, DOB, account #s). No app-layer envelope encryption; Postgres volume not LUKS/KMS in compose. Add column-level encryption (Fernet w/ KMS-held DEK) for high-sensitivity fields; enable disk encryption. (`backend/db/models/loan.py:64,81-110`)
- **[HIGH]** `ssn_hash` column declared "salted hash" but no code path writes it. Meanwhile, the classifier extracts SSN/last-4 into `Document.extracted_data` JSONB unencrypted (cross-doc correlation is trivial). Drop SSN extraction, OR encrypt the sidecar, OR HMAC-with-KMS-pepper. (`backend/db/models/loan.py:93`, `backend/agents/document_classifier/prompts.py:44`)
- **[HIGH]** `SQLAlchemy echo=True` in dev logs every query incl. emails + bcrypt hashes to stdout. Decouple from `APP_ENV`; gate behind a separate `SQL_ECHO` env defaulting off. (`backend/db/postgres.py:12`)
- **[HIGH]** Anthropic receives **raw PDF text and raw base64 of borrower images** (driver's license face + DL#). Becomes a GLBA service provider; needs a signed DPA + Zero-Data-Retention configured + redaction layer. Add PII regex redaction (SSN/DOB/account#) before send; per-tenant opt-in for cloud LLM; default deny. (`backend/agents/document_classifier/agent.py:159-189`)
- **[HIGH]** No tenant isolation at storage layer — single MinIO bucket with directory prefix. App-bug or rogue admin = cross-tenant access. Bucket-per-tenant OR STS-scoped credentials with prefix-bound IAM. (`backend/shared/storage.py`)

## 6. Webhooks & External Integrations

- **[CRITICAL]** Webhook HMAC verifier returns `True` when secret is unset. Deploy without secret → anyone on the internet spoofs milestone changes (incl. "Clear to Close"). Fail-closed; refuse startup if non-dev and secret missing. (`backend/services/encompass/client.py:222-234`)
- **[HIGH]** No replay protection — no `X-Encompass-Timestamp` skew check, no nonce store. Add ±5min skew bound + Redis-backed nonce cache.
- **[HIGH]** Webhook handler is not idempotent — no event-id dedupe table. Encompass replays will re-apply state. Add `UNIQUE(instance_id, event_id)` ledger. (`backend/routers/webhooks.py:36-76`)
- **[HIGH]** `_get_or_create_loan` race: two concurrent webhooks for a new Encompass loan both pass the `select`, second INSERT fails. Use `ON CONFLICT (encompass_loan_id) DO UPDATE … RETURNING …` or advisory lock. (`backend/routers/webhooks.py:153-170`)
- **[HIGH]** Auto-create placeholder loans on unknown Encompass IDs → DoS / DB pollution. Require explicit provisioning.
- **[HIGH]** Webhook returns 200 even with no registered handler — Encompass thinks delivery succeeded. (`backend/routers/webhooks.py:73-76`)
- **[MEDIUM]** Encompass client TLS not pinned; no mTLS; no client retry on 5xx/timeouts; no circuit breaker. Pin cert chain, add 5xx retry, request budget. (`backend/services/encompass/client.py:37-101`)
- **[MEDIUM]** `EncompassClient` instantiated per-webhook (only used to verify HMAC — does not need a client). Extract `verify_webhook_signature` to a free function. (`backend/routers/webhooks.py:44-49`)

## 7. LLM, Prompt, and Agent Reliability

- **[HIGH]** No prompt-injection defenses: borrower text fed verbatim into prompt. Add input delimiters + system meta-instruction; validate LLM output against tight Pydantic schemas; cap field ranges (wages > $10M = quality issue); compare LLM-extracted vs deterministic checks.
- **[HIGH]** No hallucination guardrails on financial values: `extracted_data["wages_box1"]` etc. flow straight into DTI/LTV/AI-readiness. Add per-field schema, min/max bounds, citation requirement, confidence-per-field. (`backend/services/loan_metrics.py`)
- **[HIGH]** Anthropic `json_mode` is string-appended to system prompt (`"\n\nYou must respond with valid JSON only…"`). Switch to native tool-use / structured outputs. (`backend/shared/llm.py:358-359`)
- **[HIGH]** DeepEval test scaffolding is placeholder only — `actual_output = expected_answer` in every eval. No real agent evals run. Wire a classifier golden corpus + eval gate. (`backend/tests/evals/test_agent_eval.py`)
- **[HIGH]** Retry/backoff only implemented for `AnthropicProvider`. Ollama/vLLM/LiteLLM/OpenAI providers do single-shot. Hoist into a shared `_retry_request` helper. (`backend/shared/llm.py:79-296`)
- **[HIGH]** LLM provider created + closed per call — six `httpx.AsyncClient` allocations per validation graph traversal. Cache singletons. (`backend/agents/cross_doc_validator/graph.py:177-250`)
- **[HIGH]** `BaseAgent` instantiates Langfuse client at module import even when keys are empty; the `_traced` decorator's `__init_subclass__` overrides `run` and silently breaks signature for subclasses with different params. Lazy-init Langfuse; switch to a context-manager API. (`backend/agents/base_agent.py:16-51`)
- **[HIGH]** No prompt versioning — prompts are inline strings; no `PROMPT_VERSION` recorded with `AgentValidation` rows. Add a registry + version tag.
- **[HIGH]** Anthropic enabled whenever the key is set — no per-tenant opt-in. Many banks require "no cloud LLM"; needs admin toggle. (`backend/agents/document_classifier/agent.py:73-82`)
- **[MEDIUM]** No token-budget check before sending big PDFs; 20-page cap mitigates somewhat but a 150-page filing post-extraction can still exceed context.
- **[MEDIUM]** Anthropic key passed via `httpx` default `Authorization` header — can leak into exception serialization. Pass per-request. (`backend/shared/llm.py:255-258`)
- **[MEDIUM]** Default model `claude-sonnet-4-6` hardcoded in source. Expose as `ANTHROPIC_MODEL` setting. (`backend/shared/llm.py:311,455`)
- **[MEDIUM]** "Deterministic rules vs LLM" boundary is leaky — `cross_doc_validator/graph.py` makes ~6 LLM calls per loan for things that can be deterministic (SSN-last-4 + DOB match, employer name fuzz). Convert to code + LLM tiebreaker only. (`backend/agents/cross_doc_validator/graph.py:163-374`)
- **[MEDIUM]** Classifier filename-heuristic fallback has no metric. Emit `classifier_fallback_filename` counter. (`backend/agents/document_classifier/agent.py:202-221`)

## 8. State, Consistency, Idempotency

- **[CRITICAL]** Classifier "silent success" bug: pre-typed uploads are unconditionally set to `status=CLASSIFIED` on the success path, even when `extracted_data == {}`. Downstream income calc / validation operate on empty payloads and a UW may approve. Require non-empty extraction + no critical quality issues before `CLASSIFIED`; else `NEEDS_REVIEW`. (`backend/agents/document_classifier/agent.py:313-318`)
- **[HIGH]** Classifier mutates status across two DB sessions with a long LLM call in between; if the process dies, the row is stuck in `CLASSIFYING`. Add a janitor that re-queues `CLASSIFYING > N min`, with `processing_lease_expires_at` + `attempts` columns.
- **[HIGH]** `recalculate_loan_metrics` has no per-loan lock — two concurrent classifications produce racy writes to `loan.ai_readiness_score`. PG advisory lock or Redis Redlock. (`backend/services/loan_metrics.py:643`)
- **[HIGH]** Double-commit pattern: `get_db` auto-commits and routers also explicitly commit (e.g. `documents.py:146`). Pick one ownership model. (`backend/db/postgres.py:18-24`)
- **[MEDIUM]** `DocumentStatus` enum has both `CLASSIFIED` and `EXTRACTED` but the classifier never transitions to `EXTRACTED`. Use it or remove. (`backend/shared/types.py:115,117`)

## 9. Data Model

- **[HIGH]** No `ON DELETE CASCADE` foreign keys anywhere. `delete_loan` works around it with 5 explicit deletes — fragile. Add `ondelete="CASCADE"` + Alembic migration. (`backend/db/migrations/versions/d5fa944353bb_initial_schema.py`)
- **[HIGH]** No `(tenant_id, id)` composite indexes; every tenant-scoped query filters on both. Add or partition. (`backend/routers/loans.py:370`)
- **[HIGH]** No `UNIQUE(loan_id, file_hash)` — race between concurrent identical uploads inserts both. (`backend/routers/documents.py:103-107`)
- **[HIGH]** No history on mutated financial fields (`loans.ltv`, `dti_back`, `qualifying_income_monthly`). Auditors will reject "what was the decision-time value?". Shadow-history table or snapshot in `agent_validations.result`. (`backend/services/loan_metrics.py:713-756`)
- **[HIGH]** No soft-deletes; hard-deletes destroy audit evidence on regulated data. Add `deleted_at` + `deleted_by_user_id`; admin "purge" job for retention.
- **[HIGH]** `period_start`/`period_end` stored as `VARCHAR(10)`, parsed on every metric recalc — malformed string silently drops the value. Use `Date`. (`backend/db/models/document.py:47-48`)
- **[MEDIUM]** `AuditEvent.tenant_id` has no FK constraint. (`backend/db/models/audit.py:17`)
- **[MEDIUM]** No index on `Document.status` / `Document.borrower_id`.
- **[MEDIUM]** Audit table grows unboundedly; partition by month or move to timeseries store.
- **[LOW]** `Condition.metadata` column collides with SQLAlchemy reserved attribute; mapped via `mapped_column("metadata", …)`. Rename. (`backend/db/models/condition.py:44`)

## 10. Scalability & Concurrency

- **[HIGH]** DB engine uses asyncpg defaults (`pool_size=5`, no pre-ping, no recycle). Concurrent SSE + uploads + background tasks will starve. Tune via env. (`backend/db/postgres.py:12`)
- **[HIGH]** SSE pub/sub is an in-process dict (`_subscribers`). Multi-worker / multi-pod = events never reach subscribers on other workers. Replace with Redis pub/sub (Redis is already in compose, unused). (`backend/events/sse.py:15`)
- **[HIGH]** SSE never sends keepalives — proxies (nginx/ALB) silently 504. Unbounded subscriber map = memory leak. Send `: keepalive\n\n` every 15s; cap subs per loan/user. (`backend/events/sse.py:31-53`)
- **[HIGH]** `fastapi.BackgroundTasks` used for long LLM-bound work: in-process, lost on crash, no retry, blocks graceful shutdown, cannot scale workers separately from API. Move to Arq/Celery/Temporal (already aspirational per webhook comment). (`backend/routers/documents.py:156`, `backend/routers/loans.py:296-314`)
- **[HIGH]** Storage clients (S3/GCS/Azure) do blocking I/O inside `async def`. Use `asyncio.to_thread` or aio-libs. (`backend/shared/storage.py:50-149`)
- **[HIGH]** Document upload reads the entire file into memory + duplicates it into the background-task closure. 100MB upload = ~200MB resident per request. Stream to storage, pass key only to the task. (`backend/routers/documents.py:99`)
- **[MEDIUM]** `list_loans` does N+1 (`COUNT` subqueries inside a Python loop). One `GROUP BY` query. (`backend/routers/dashboard.py:84-103`)

## 11. Observability & Logging

- **[HIGH]** No structured logging — default uvicorn text. Add `structlog` or `python-json-logger`. (`backend/main.py:13`)
- **[HIGH]** No correlation-id middleware; background tasks have no trace linkage. Add `asgi-correlation-id`; bind to Langfuse `session_id`.
- **[HIGH]** No `/metrics`, no Prometheus exporter, no OTel instrumentation. Add `prometheus-fastapi-instrumentator`; emit custom counters (encompass_rate_limit_hits, llm_retry, classifier_outcome).
- **[HIGH]** `/health` is liveness only — no readiness against Postgres/Redis/MinIO/LLM. Add `/health/ready`. (`backend/routers/health.py:8-10`)
- **[HIGH]** AuditEvent only written on webhooks; no login/logout/role-change/upload/delete/validate audit. GLBA/SOC2 cannot be satisfied without coverage. Add a middleware-level `@audit` decorator. (`backend/routers/webhooks.py:62-71`)
- **[HIGH]** Audit table is mutable. No hash chain, no WORM. Add `prev_hash` chaining; nightly export to S3 Object Lock; write-only DB role.
- **[HIGH]** No "who-saw-what" audit on document downloads (GLBA/CCPA-relevant). (`backend/routers/documents.py:183-214`)
- **[MEDIUM]** HTTPException details leak raw exception strings to clients (`detail=str(e)` in upload + Azure handlers). Standard error envelope; map exceptions in a global handler.
- **[MEDIUM]** No error-code taxonomy — `frontend/lib/api.ts:68-69` throws on free-form `detail` strings.
- **[MEDIUM]** `logger.info(f"Webhook received: ... data={event.data}")` may log borrower payloads. Redact. (`backend/routers/webhooks.py:54`)

## 12. Network & Infrastructure

- **[CRITICAL]** CORS `allow_origins=["*"]` with `allow_credentials=True` when `app_env=="dev"`. Wildcard+credentials is a misconfiguration browsers refuse, but ACAO mirroring + `Authorization` header reads still let any origin read API responses on behalf of a logged-in user. Default to explicit allow-list; refuse to start in non-dev with empty list. (`backend/main.py:38-44`)
- **[HIGH]** No HSTS / CSP / X-Frame-Options / Referrer-Policy / Permissions-Policy headers. Add `secure-headers` middleware + reverse-proxy enforced HSTS.
- **[HIGH]** No global rate limit / abuse middleware. SSE subscribers can grow unbounded.
- **[HIGH]** `/docs`, `/redoc` enabled when `app_env=="dev"`. Pilot environments running with dev env leak full API surface. Tie to a separate `ENABLE_DOCS` env, default off. (`backend/main.py:26-27`)
- **[HIGH]** Backend Dockerfile runs as root; no `USER` directive. Add non-root user. (`backend/Dockerfile`)
- **[HIGH]** Frontend Dockerfile runs `npm run dev` in container (HMR, source maps, no minification). `next.config.ts` already declares `output: "standalone"` — wire it: `npm ci && npm run build && node .next/standalone/server.js`. (`frontend/Dockerfile:16`)
- **[HIGH]** Dockerfile is single-stage; no committed `uv.lock`; no `--frozen` install. Multi-stage builder + frozen lock + non-root runtime.
- **[HIGH]** `docker-compose.yml` bind-mounts `../backend:/app/backend` — production stacks must not. Split `docker-compose.dev.yml` (mounts) from `docker-compose.yml` (no mounts). (`infra/docker-compose.yml:14`)
- **[HIGH]** Migrations run in serving container at start (`entrypoint.sh:5` `alembic upgrade head`). Move to dedicated job/Kubernetes Job; serving container does `alembic current` check only. (`backend/entrypoint.sh:5`)
- **[MEDIUM]** All base images unpinned (`postgres:16`, `redis:7-alpine`, `minio/minio:latest`, `langfuse/langfuse:latest`, `ngrok/ngrok:latest`, `python:3.11-slim`, `node:20-alpine`). Pin to digests; Renovate + Trivy in CI.
- **[MEDIUM]** `ngrok` profile in compose tunnels backend to the public internet. Remove from prod compose; doc as dev-only.
- **[MEDIUM]** No TLS at FastAPI layer; assumes reverse proxy but none provided. Add nginx/Caddy + TLS 1.2+ baseline to prod compose.
- **[MEDIUM]** No `SIGTERM` drain for SSE connections or background tasks. Add lifespan shutdown handler.
- **[LOW]** MinIO bucket lacks explicit `mc anonymous set none`.

## 13. API Design

- **[HIGH]** No API versioning — every route mounted under `/api/` with no `/v1/`. Prefix all mounts. (`backend/main.py:48-52`)
- **[HIGH]** Inconsistent error shapes; no unified `{error: {code, message, fields}}` envelope.
- **[HIGH]** No pagination contracts — `list_loans` takes `limit/offset` but returns a bare array, no `total`, no `next`. (`backend/routers/loans.py:108-154`)
- **[HIGH]** Filter/search is missing on pipeline (persona, LO, FICO, DTI). (`backend/routers/dashboard.py:64-131`)
- **[MEDIUM]** `POST /loans/{id}/validate` returns `{"message": "Validation started"}` — no job id to poll. Return `{job_id, status_url}`. (`backend/routers/loans.py:296-314`)
- **[MEDIUM]** Webhooks return 200 even when no handler. Return 4xx so Encompass replays.
- **[LOW]** Bare-list vs `{items, total}` response shape inconsistent across endpoints.

## 14. Frontend

- **[CRITICAL]** Access + refresh JWTs in `localStorage`; vulnerable to any XSS payload (uploaded SVG via inline doc serving, dep-chain compromise, etc.). 7-day non-revokable refresh. Move to `HttpOnly; Secure; SameSite=Strict` cookies + CSRF protection. (`frontend/lib/auth.ts:27-30`, `frontend/lib/api.ts:30-32`)
- **[HIGH]** SSE token in query string — leaks into proxy access logs, browser history, referer. Signed cookie or one-time URL handshake. (`frontend/lib/api.ts:454,466`)
- **[HIGH]** No Content Security Policy; Next.js sets none by default. Add strict CSP via `next.config.ts` headers().
- **[HIGH]** All pages `"use client"` (1061 LOC of client code in `[loanId]/page.tsx`). Move data fetching to RSC; no SEO/streaming today.
- **[HIGH]** `pdfjs-dist` 5.6.x + `react-pdf` — verify worker is sandboxed (`isEvalSupported: false`) given borrower PDFs are rendered inline.
- **[MEDIUM]** No typed error contract; `lib/api.ts:68-69` throws on free-form `detail`. Add `ApiError` class with code + status.
- **[MEDIUM]** No global error boundary or toast pattern.
- **[MEDIUM]** `@tanstack/react-query` in deps but unused; hand-rolled fetch wrapper duplicates caching/refresh. Pick one.
- **[MEDIUM]** No accessibility primitives; custom tables without `<caption>`/aria; no skip-to-content.
- **[LOW]** `console.warn` operational details in `api.ts`.
- **[LOW]** `NEXT_PUBLIC_API_URL=http://localhost:8000` baked into prod compose. Use relative `/api`.

## 15. Testing

- **[CRITICAL]** Effectively zero coverage. Only real test: `test_health.py` (16 lines). No tests for auth, loans, documents, webhooks, tenant scoping, RBAC, classifier, validator, or **`loan_metrics.py`** (the regulatory math). Minimum: FNMA income waterfall + LTV/DTI/PMI math + tenant-isolation integration.
- **[HIGH]** `infra/docker-compose.test.yml` exists but is unreferenced. No `conftest.py`, no testcontainers fixture.
- **[HIGH]** No `.github/workflows` / `.gitlab-ci.yml`. Tests not gated. Add lint/typecheck/test/alembic-check/`pip-audit`/`npm audit`/Trivy.
- **[HIGH]** DeepEval scaffolding is all `actual_output = expected_answer` placeholders. Wire real agent invocations with golden corpus. (`backend/tests/evals/test_agent_eval.py`)
- **[MEDIUM]** `pytest-asyncio` mode=auto with no session-scoped event-loop fixture — flaky with multi-DB tests.
- **[MEDIUM]** No load tests for SSE; no contract tests for Encompass webhook payloads.

## 16. Dependencies & Supply Chain

- **[HIGH]** No committed `uv.lock`. Builds non-reproducible.
- **[HIGH]** `python-jose >= 3.3` allows CVE-2024-33663/33664 vulnerable 3.3.x. Pin `>=3.4.0` or remove jose.
- **[HIGH]** `passlib` unmaintained — replace with bcrypt/argon2 directly.
- **[HIGH]** **MinIO is AGPL-3.0** — copyleft implications when integrated into a distributed product. Evaluate Ceph / SeaweedFS / managed S3 for production.
- **[MEDIUM]** `langchain >= 0.2` had SSRF / code-exec CVEs (`PALChain`, `PythonREPL`). Confirm not in use; pin `>=0.3`.
- **[MEDIUM]** `pypdf >= 4.0` has DoS CVEs on malformed PDFs. Pin `>=5.1` (20-page cap helps but doesn't fix parser).
- **[MEDIUM]** `anthropic >= 0.30` unbounded — pin a tested range.
- **[MEDIUM]** `pydantic[email] >= 2.0`, `next ^15.1`, `react ^19.0`, `langfuse >= 2.0`, `langgraph >= 0.2` all floating. Pin.
- **[MEDIUM]** No `pip-audit` / `npm audit` / Trivy gate in CI.
- **[LOW]** `python-multipart` — confirm `>=0.0.18` (CVE-2024-53981).

## 17. Documentation

- **[MEDIUM]** No top-level `README.md` (only `docs/README.md` + a single ADR template).
- **[MEDIUM]** No filed ADRs for material decisions (Ollama-first, in-process SSE, agent boundary, multi-tenant default tenant).
- **[MEDIUM]** No runbook for: rotating JWT secret, replaying webhooks, reprocessing stuck `CLASSIFYING` docs, classifier backlog, key rotation.
- **[LOW]** `CLAUDE.md` (backend + frontend) substitute for `docs/architecture.md`; they are agent-onboarding, not human-onboarding.

## 18. Compliance & Operational

- **[HIGH]** No data retention / purge policy implementation. GLBA requires retention schedules + secure disposal. Scheduled per-tenant purge job; storage tombstoning.
- **[HIGH]** No documented incident response / breach notification (GLBA 30-day rule).
- **[MEDIUM]** No segregation-of-duties enforcement — the same LO can create, classify, and validate. Block self-validation; require separate-actor sign-off on `Clear to Close`.

---

## Suggested phasing

| Phase | Window | Scope |
|---|---|---|
| **0 — Stop the bleed** | Week 1 | Rotate Anthropic key + all default creds. Make JWT secret + webhook HMAC fail-closed. Make registration invite-only. Disable `/docs` outside explicit dev. Tighten CORS to allow-list. |
| **1 — Pilot-ready** | Weeks 2-6 | Items in §1, §2, §3 (CRITICAL+HIGH), file-upload hardening, SSE auth+tenant scoping, Azure JWKS verification, replace `BackgroundTasks` with a real queue, fix classifier pre-typed bug, structured logs + correlation id, role checks on every router, soft-deletes + audit coverage. |
| **2 — Enterprise pilot** | Weeks 7-12 | Encryption at rest, PII redaction before LLM, per-tenant LLM opt-in, vault wiring for Encompass secrets, eval harness for classifier, prompt versioning, idempotent webhooks, Redis-backed SSE w/ keepalives, multi-stage Dockerfiles, CI with pip-audit/npm-audit/Trivy, test coverage for `loan_metrics.py`, blue/green-safe migrations. |
| **3 — GA / SOC 2** | Quarter 2 | Tamper-evident audit, append-only audit storage, retention enforcement, row-level security as defense-in-depth, MinIO replacement (AGPL), partitioned audit, segregation-of-duties controls, dependency lock + SBOM + signed images, runbooks + ADRs, incident-response playbook. |
