# Deploying mortgage-intelligence to Render

This is a hosted-trial deploy: prospects can sign up, get their own isolated
tenant, and upload **synthetic** loan documents. It is **not** a production
deploy — see [improvements.md](../improvements.md) for the full GLBA-readiness
checklist before any real borrower data hits the system.

---

## What gets deployed

| Component | Render service | Plan | Notes |
|---|---|---|---|
| Backend (FastAPI) | Web Service, Docker | Starter ($7/mo) | runs migrations + uvicorn on `$PORT` |
| Frontend (Next.js) | Web Service, Docker | Starter ($7/mo) | production build, non-root |
| Postgres 16 | Managed DB | Starter ($7/mo) | required for >90-day persistence |
| Object storage | **Cloudflare R2** (external) | ~$0 at trial scale | S3-compatible, free egress |
| LLM | Anthropic API (optional) | per-token | tenant-opt-in toggle TBD |

Estimated monthly: **~$21 Render + R2 storage + Anthropic usage**.

---

## One-time setup

### 1. Cloudflare R2 bucket

1. Cloudflare dashboard → **R2** → **Create bucket**: `mortgage-intelligence-trial`.
2. **Manage R2 API Tokens** → **Create API Token** → permissions: *Object Read & Write*,
   scoped to the bucket only. Save the **Access Key ID** + **Secret Access Key**.
3. Note your **account ID** (Cloudflare dashboard sidebar). The S3 endpoint URL is:
   `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`

### 2. Render environment group

In the Render dashboard → **Environment Groups** → **New Group**:

- **Name:** `mortgage-intelligence-secrets`
- **Variables:**

| Key | Value |
|---|---|
| `STORAGE_PROVIDER` | `s3` |
| `STORAGE_BUCKET` | `mortgage-intelligence-trial` |
| `STORAGE_REGION` | `auto` |
| `STORAGE_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `STORAGE_ACCESS_KEY` | *(from R2 token)* |
| `STORAGE_SECRET_KEY` | *(from R2 token)* |
| `ANTHROPIC_API_KEY` | *(optional — your Anthropic key)* |
| `LANGFUSE_PUBLIC_KEY` | *(optional)* |
| `LANGFUSE_SECRET_KEY` | *(optional)* |
| `LANGFUSE_HOST` | *(optional, e.g. `https://cloud.langfuse.com`)* |

⚠️ Do **not** commit these values to git. The `render.yaml` references the group
by name only.

### 3. Blueprint deploy

1. Push this branch to GitHub.
2. Render dashboard → **New** → **Blueprint** → connect the repo → select branch.
3. Render reads [`render.yaml`](../render.yaml) and creates the DB + both services.
4. First deploy will **fail** for the backend because `ALLOWED_ORIGINS` is not set yet —
   that is expected. Continue to step 4.

### 4. Wire the two services together

After both services have a URL:

1. Open the **backend** service → **Environment** → set:
   - `ALLOWED_ORIGINS` = the frontend URL, e.g.
     `https://mortgage-intelligence-frontend.onrender.com`
     (comma-separated if you add a custom domain later — no wildcards).
2. Open the **frontend** service → **Environment** → set:
   - `NEXT_PUBLIC_API_URL` = the backend URL, e.g.
     `https://mortgage-intelligence-backend.onrender.com`
3. **Manual Deploy → Clear build cache & deploy** on both services.

### 5. Smoke test

```sh
# Replace with your Render URLs.
curl -sf https://mortgage-intelligence-backend.onrender.com/health
# → {"status":"ok"}

curl -sf -X POST https://mortgage-intelligence-backend.onrender.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"correct-horse-battery","name":"Demo"}'
# → 201 with access_token / refresh_token
```

Then open the frontend URL in a browser, register, and upload a sample PDF.

---

## What this deploy enforces

The pre-deploy hardening that landed alongside this config:

- ✅ JWT secret fails fast if defaulted in `APP_ENV != dev`
   ([`backend/core/config.py`](../backend/core/config.py))
- ✅ `/auth/register` server-assigns role + creates a fresh isolated tenant per signup —
   client cannot self-elect `ADMIN` ([`backend/routers/auth.py`](../backend/routers/auth.py))
- ✅ Rate limits on `/login` (10/min), `/register` (5/min), `/refresh` (30/min)
   via slowapi ([`backend/core/rate_limit.py`](../backend/core/rate_limit.py))
- ✅ Upload size cap (25 MiB), MIME allow-list (PDF / JPEG / PNG / TIFF),
   magic-byte sniff, sanitized filenames, forced `attachment` for non-image/PDF
   ([`backend/routers/documents.py`](../backend/routers/documents.py))
- ✅ CORS allow-list (no wildcard in production)
   ([`backend/main.py`](../backend/main.py))
- ✅ Security headers: `X-Content-Type-Options`, `X-Frame-Options`, HSTS in prod
- ✅ Tenant-scoped SSE channels + explicit token verification (no more global
   `pipeline` broadcast) ([`backend/events/sse.py`](../backend/events/sse.py))
- ✅ `/docs` + `/redoc` disabled when `APP_ENV != dev`
- ✅ SQL `echo` decoupled from `APP_ENV` (defaults off)

---

## What this deploy does **not** cover

These are still open and **must** be closed before accepting any real borrower data:

- ❌ HS256 JWT with single secret for access + refresh — move to RS256/EdDSA from KMS
- ❌ No refresh-token rotation / revocation
- ❌ Azure AD `id_token` signature still unverified
- ❌ Webhook HMAC verifier is fail-open (only matters when Encompass is wired in)
- ❌ PII columns plaintext at rest — no envelope encryption
- ❌ JWT in `localStorage` on the frontend — XSS-recoverable
- ❌ `fastapi.BackgroundTasks` not durable — a backend redeploy kills in-flight
   classifications. Move to Arq/Temporal.
- ❌ SSE pub/sub is in-process — only works because this deploy is single-replica.

See [`improvements.md`](../improvements.md) for the full list.

---

## Trial guardrails to set with prospects

Before sharing the URL:

1. **Custom domain** (e.g. `trial.your-company.com`) so the link looks legitimate.
2. **Click-through ToS** at signup: "synthetic / non-NPI test data only;
   uploads may be reviewed and deleted; service is provided as-is for evaluation."
3. **Watermark banner** on every page (set `TRIAL_MODE=true`):
   *"Evaluation environment — do not upload real borrower data."*
4. **Periodic data sweep**: a scheduled job that deletes loans + documents
   older than 30 days. Not implemented yet — track as a follow-up.

---

## Operations

- **Logs**: Render dashboard → service → Logs. Streamed in real-time.
- **Restart**: Render dashboard → service → Manual Deploy → *Deploy latest commit*.
- **DB shell**: Render dashboard → DB → *Connect* → *PSQL Command*.
- **Backups**: Starter Postgres has daily backups for 7 days. Bump plan for longer.
- **Secrets rotation**: change the value in the `mortgage-intelligence-secrets`
   env group → Render auto-redeploys both services.

---

## Rolling back

```sh
# In the Render dashboard:
# Backend service → Deploys → click a previous successful deploy → "Rollback to this deploy"
```

Database migrations are not auto-reverted. If a migration ships with bad
behavior, write a forward-migration that undoes it rather than rolling back
the schema.
