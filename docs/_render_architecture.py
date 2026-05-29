"""Render mortgage-intelligence architecture diagrams (current + future) as PNGs.

Run with: uvx --from matplotlib python docs/_render_architecture.py
Outputs:   docs/architecture_current.png, docs/architecture_future.png
"""
from __future__ import annotations

import os

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def box(ax, x, y, w, h, label, *, face="#E8F0FE", edge="#1A73E8", fontsize=8, weight="normal", zorder=2):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.2, edgecolor=edge, facecolor=face, zorder=zorder,
    )
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
            fontsize=fontsize, fontweight=weight, wrap=True, zorder=zorder + 1)


def group(ax, x, y, w, h, label, *, face="#FAFAFA", edge="#9AA0A6"):
    p = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        linewidth=1.0, linestyle="--", edgecolor=edge, facecolor=face, zorder=1,
    )
    ax.add_patch(p)
    ax.text(x + 0.15, y + h - 0.28, label, ha="left", va="top",
            fontsize=9, fontweight="bold", color=edge, zorder=2)


def arrow(ax, x1, y1, x2, y2, label=None, *, color="#202124", style="-|>", lw=1.1,
          ls="-", curve=0.0, label_pos=0.5, label_offset=(0, 0.15), label_size=7):
    cs = f"arc3,rad={curve}"
    a = FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=style, mutation_scale=10,
        linewidth=lw, color=color, linestyle=ls, connectionstyle=cs, zorder=5,
    )
    ax.add_patch(a)
    if label:
        lx = x1 + (x2 - x1) * label_pos + label_offset[0]
        ly = y1 + (y2 - y1) * label_pos + label_offset[1]
        ax.text(lx, ly, label, ha="center", va="center", fontsize=label_size,
                color=color, style="italic", zorder=6,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))


def new_fig(title):
    fig, ax = plt.subplots(figsize=(18, 11))
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 11)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(9, 10.65, title, ha="center", va="center", fontsize=15, fontweight="bold")
    return fig, ax


# ---------------------------------------------------------------------------
# CURRENT ARCHITECTURE
# ---------------------------------------------------------------------------
def draw_current():
    fig, ax = new_fig("mortgage-intelligence — Current Architecture (as built)")

    ax.text(9, 10.25,
            "Single FastAPI process · in-process agents + BackgroundTasks · SSE in-process pub/sub · "
            "column-scoped multi-tenancy",
            ha="center", va="center", fontsize=9, color="#5F6368", style="italic")

    # Clients / external
    box(ax, 0.4, 8.8, 3.0, 0.9, "Browser (Next.js SPA)\nJWT in localStorage", face="#FFF8E1", edge="#F9AB00")
    box(ax, 0.4, 7.5, 3.0, 0.9, "Encompass\n(LO system)", face="#FFF8E1", edge="#F9AB00")

    # FastAPI monolith group
    group(ax, 4.0, 1.6, 9.6, 8.4, "FastAPI monolith (uvicorn, single process)")

    # Routers
    box(ax, 4.3, 8.7, 9.0, 1.0,
        "routers/   auth · loans · documents · dashboard · webhooks · health\n"
        "(CORS *, query-string SSE token, inline if/role checks)",
        face="#E8F0FE", edge="#1A73E8")

    # SSE layer
    box(ax, 4.3, 7.6, 4.3, 0.9,
        "events/sse.py\nin-process `_subscribers` dict\n(no Redis, no keepalive)",
        face="#FCE8E6", edge="#D93025")
    # BackgroundTasks
    box(ax, 8.9, 7.6, 4.4, 0.9,
        "fastapi.BackgroundTasks\n(in-process workers, no retry/lease/DLQ)",
        face="#FCE8E6", edge="#D93025")

    # Agents row
    box(ax, 4.3, 6.0, 9.0, 1.3,
        "agents/  (extend BaseAgent → auto Langfuse trace)\n"
        "orchestrator · document_classifier · cross_doc_validator · income_calculator\n"
        "asset_verifier · employment_verifier · credit_analyzer · compliance_qc · uw_package_builder",
        face="#E6F4EA", edge="#188038")

    # Services row
    box(ax, 4.3, 4.6, 4.3, 1.0,
        "services/encompass/client.py\n(OAuth2 · fail-open HMAC · hardcoded tenant_id)",
        face="#E8F0FE", edge="#1A73E8")
    box(ax, 8.9, 4.6, 4.4, 1.0,
        "services/loan_metrics.py · services/rules/\nDeterministic FNMA math, checklists, conditions",
        face="#E8F0FE", edge="#1A73E8")

    # Shared adapters
    box(ax, 4.3, 3.3, 4.3, 1.0,
        "shared/llm.py — pluggable provider\n(Ollama · vLLM · OpenAI · Anthropic)",
        face="#F3E8FD", edge="#7627BB")
    box(ax, 8.9, 3.3, 4.4, 1.0,
        "shared/storage.py — pluggable\n(Local · MinIO · S3 · GCS · Azure)",
        face="#F3E8FD", edge="#7627BB")

    # Auth
    box(ax, 4.3, 2.0, 9.0, 1.0,
        "auth/azure_ad.py (id_token NOT verified) · dependencies.py (JWT HS256, single secret)\n"
        "require_role() defined but unused on most routes",
        face="#FCE8E6", edge="#D93025")

    # Right-side data plane (docker-compose)
    group(ax, 14.0, 1.6, 3.8, 8.4, "docker-compose data plane")
    box(ax, 14.2, 8.8, 3.5, 0.9, "PostgreSQL 16\nasyncpg · single schema\ntenant_id column", face="#E8F0FE", edge="#1A73E8")
    box(ax, 14.2, 7.7, 3.5, 0.9, "Redis 7\n(running, but UNUSED\nin this arch)", face="#FEFEFE", edge="#80868B")
    box(ax, 14.2, 6.6, 3.5, 0.9, "MinIO (S3-compat)\nsingle bucket\nprefix-per-tenant", face="#E8F0FE", edge="#1A73E8")
    box(ax, 14.2, 5.4, 3.5, 1.0, "Langfuse\ntraces (per-agent)\nself-hosted, MIT", face="#F3E8FD", edge="#7627BB")
    box(ax, 14.2, 4.0, 3.5, 1.1, "External LLM\n(Anthropic / Ollama)\nNo tenant opt-in, no PII redaction", face="#FFF8E1", edge="#F9AB00")
    box(ax, 14.2, 2.0, 3.5, 1.8,
        "Risks today:\n• default JWT secret\n• fail-open webhook HMAC\n• SSE unauth + cross-tenant\n• PII plaintext\n• BackgroundTasks lost on crash",
        face="#FCE8E6", edge="#D93025", fontsize=7)

    # ----- Arrows (code flow) -----
    # Browser → routers
    arrow(ax, 3.4, 9.25, 4.3, 9.25, "HTTPS · JWT", label_offset=(0, 0.15))
    # Browser ← SSE
    arrow(ax, 4.3, 8.05, 3.4, 8.95, "SSE (token in query string)",
          color="#D93025", curve=-0.2, label_pos=0.4, label_offset=(0.4, 0.1))
    # Encompass → routers
    arrow(ax, 3.4, 7.95, 4.3, 8.85, "webhook (HMAC)", curve=0.15, label_offset=(0.2, 0.1))

    # Routers → SSE
    arrow(ax, 6.5, 8.7, 6.5, 8.5, color="#5F6368")
    # Routers → BackgroundTasks
    arrow(ax, 11.0, 8.7, 11.0, 8.5, "enqueue", color="#5F6368", label_offset=(0.6, 0))
    # BackgroundTasks → agents
    arrow(ax, 11.0, 7.6, 11.0, 7.3, color="#188038")
    # Routers → agents (direct call paths exist too)
    arrow(ax, 6.5, 8.7, 6.5, 7.3, color="#188038", curve=0.0)
    # Agents → services
    arrow(ax, 6.5, 6.0, 6.5, 5.6, color="#1A73E8")
    arrow(ax, 11.0, 6.0, 11.0, 5.6, color="#1A73E8")
    # services → shared (LLM/storage)
    arrow(ax, 6.5, 4.6, 6.5, 4.3, color="#7627BB")
    arrow(ax, 11.0, 4.6, 11.0, 4.3, color="#7627BB")
    # agents → shared/llm (more directly)
    arrow(ax, 5.6, 6.0, 5.6, 4.3, color="#7627BB", curve=0.1)

    # services → DB (Postgres)
    arrow(ax, 8.6, 5.1, 14.2, 9.2, "SQLAlchemy async",
          color="#1A73E8", curve=0.15, label_pos=0.6, label_offset=(0, 0.15))
    arrow(ax, 8.6, 5.1, 14.2, 7.05, color="#80868B", ls=":", curve=-0.1)
    # storage → MinIO
    arrow(ax, 13.3, 3.8, 14.2, 6.9, color="#1A73E8", curve=0.1)
    # LLM → external
    arrow(ax, 8.6, 3.8, 14.2, 4.6, color="#F9AB00", curve=-0.1, label_pos=0.5,
          label="Anthropic API (no redaction)", label_offset=(0, 0.18))
    # base_agent → langfuse
    arrow(ax, 13.3, 6.5, 14.2, 5.9, color="#7627BB", curve=0.0, label="traces", label_offset=(0, 0.15))
    # encompass client → external Encompass
    arrow(ax, 4.3, 5.1, 3.4, 7.5, color="#F9AB00", curve=-0.2)

    # Legend
    legend_y = 0.7
    ax.add_patch(mpatches.Rectangle((0.4, 0.3), 17.2, 0.9, linewidth=0.5,
                                    edgecolor="#9AA0A6", facecolor="#FFFFFF"))
    ax.text(0.55, legend_y + 0.25, "Legend:", fontsize=8, fontweight="bold")
    samples = [
        ("#1A73E8", "API / data path"),
        ("#188038", "Agent invocation"),
        ("#7627BB", "Pluggable adapter / LLM trace"),
        ("#F9AB00", "External (cloud) boundary"),
        ("#D93025", "Risk / weak boundary (see improvements.md)"),
    ]
    x_cursor = 1.4
    for color, text in samples:
        ax.add_patch(mpatches.Rectangle((x_cursor, legend_y + 0.15), 0.25, 0.2,
                                        facecolor=color, edgecolor="none"))
        ax.text(x_cursor + 0.32, legend_y + 0.25, text, fontsize=7, va="center")
        x_cursor += 3.3

    out = os.path.join(HERE, "architecture_current.png")
    fig.savefig(out, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# FUTURE ARCHITECTURE
# ---------------------------------------------------------------------------
def draw_future():
    fig, ax = new_fig("mortgage-intelligence — Future Architecture (enterprise / GLBA pilot target)")
    ax.text(9, 10.25,
            "Stateless API pods · durable job queue · Redis pub/sub · per-tenant LLM gateway · "
            "RLS + envelope crypto · WORM audit",
            ha="center", va="center", fontsize=9, color="#5F6368", style="italic")

    # Edge / gateway layer
    box(ax, 0.4, 8.6, 3.0, 1.1,
        "Browser (Next.js RSC)\nHttpOnly Secure cookies\nstrict CSP, CSRF token",
        face="#FFF8E1", edge="#F9AB00")
    box(ax, 0.4, 7.0, 3.0, 1.0,
        "Encompass (LO system)\nmTLS + signed webhooks", face="#FFF8E1", edge="#F9AB00")

    box(ax, 3.8, 8.7, 2.4, 1.0,
        "CDN / WAF / TLS", face="#E8F0FE", edge="#1A73E8", weight="bold")
    box(ax, 3.8, 7.4, 2.4, 1.0,
        "API Gateway /v1\nrate-limit · OAuth introspect\nidempotency keys",
        face="#E8F0FE", edge="#1A73E8")

    # Stateless API pods
    group(ax, 6.6, 5.8, 5.4, 4.2, "Stateless API pods (Kubernetes)")
    box(ax, 6.8, 8.9, 5.0, 1.0,
        "FastAPI /v1/* · RS256 JWT from KMS\nrequire_role on every route\nstructured logs + X-Request-Id",
        face="#E8F0FE", edge="#1A73E8")
    box(ax, 6.8, 7.7, 5.0, 1.0,
        "auth — invite-only register, refresh rotation\nAzure id_token verified vs JWKS · PKCE+state+nonce",
        face="#E6F4EA", edge="#188038")
    box(ax, 6.8, 6.5, 5.0, 1.0,
        "Adapters: shared/llm.py · shared/storage.py · encompass/\n(fail-closed HMAC, replay window, idempotency ledger)",
        face="#F3E8FD", edge="#7627BB")

    # Agent worker pool
    group(ax, 6.6, 1.6, 5.4, 3.8, "Agent worker pool (separate deployment)")
    box(ax, 6.8, 4.4, 5.0, 0.9,
        "Job consumer (Arq / Temporal)\nretry · lease · DLQ · idempotency",
        face="#FCE8E6", edge="#D93025", weight="bold")
    box(ax, 6.8, 3.3, 5.0, 1.0,
        "Agents (BaseAgent + prompt registry)\nclassifier · cross-doc-validator · income · asset\nVOE · credit · compliance · UW-package",
        face="#E6F4EA", edge="#188038")
    box(ax, 6.8, 2.1, 5.0, 1.0,
        "services/rules/* — deterministic FNMA math\n(LLMs extract, Python calculates — strict boundary)",
        face="#E8F0FE", edge="#1A73E8")

    # Middleware infra column
    group(ax, 12.4, 5.8, 5.4, 4.2, "Shared infra")
    box(ax, 12.6, 8.9, 5.0, 1.0,
        "Job queue (Arq / Temporal)\nat-least-once + idempotent consumers",
        face="#FCE8E6", edge="#D93025")
    box(ax, 12.6, 7.7, 5.0, 1.0,
        "Redis pub/sub\nSSE/WebSocket fan-out · keepalive\ntenant-namespaced channels",
        face="#E8F0FE", edge="#1A73E8")
    box(ax, 12.6, 6.5, 5.0, 1.0,
        "Secrets vault (SSM / Vault / Doppler)\nKMS for JWT signing + DEKs",
        face="#F3E8FD", edge="#7627BB")

    # Storage / data
    group(ax, 12.4, 1.6, 5.4, 3.8, "Stateful tier (managed / HA)")
    box(ax, 12.6, 4.3, 5.0, 1.0,
        "PostgreSQL (HA)\nRow-Level Security per tenant\ncolumn envelope encryption (SSN/DOB)\nWORM-chained audit",
        face="#E8F0FE", edge="#1A73E8")
    box(ax, 12.6, 3.0, 5.0, 1.1,
        "Object store (S3/GCS)\nbucket-per-tenant OR STS prefix\nvirus scan · server-side encryption",
        face="#E8F0FE", edge="#1A73E8")
    box(ax, 12.6, 1.7, 5.0, 1.1,
        "Observability\nOTel · Prometheus · Langfuse (per-tenant)\nSIEM-ingested audit",
        face="#F3E8FD", edge="#7627BB")

    # LLM gateway (bottom-left)
    group(ax, 0.4, 1.6, 5.8, 3.8, "LLM access (per-tenant policy)")
    box(ax, 0.6, 4.3, 5.4, 1.0,
        "LLM gateway proxy\nPII redaction · token budget\nprompt-version tag on every call\nstructured outputs (tool use)",
        face="#F3E8FD", edge="#7627BB", weight="bold")
    box(ax, 0.6, 3.1, 2.6, 1.0,
        "Self-host\nOllama / vLLM\n(default for NPI)", face="#E6F4EA", edge="#188038")
    box(ax, 3.4, 3.1, 2.6, 1.0,
        "Anthropic ZDR + DPA\n(per-tenant opt-in)", face="#FFF8E1", edge="#F9AB00")
    box(ax, 0.6, 1.7, 5.4, 1.2,
        "Tenant policy DB:\n• allow_cloud_llm: bool\n• redaction profile\n• model + budget per agent",
        face="#FCE8E6", edge="#D93025")

    # ----- Arrows -----
    # Browser → CDN → Gateway → API
    arrow(ax, 3.4, 9.1, 3.8, 9.2)
    arrow(ax, 6.2, 9.2, 6.8, 9.4, label="cookie auth")
    # Encompass → Gateway
    arrow(ax, 3.4, 7.5, 3.8, 7.9, label="mTLS")
    arrow(ax, 6.2, 7.9, 6.8, 8.2, label="webhook (verified)")

    # API → Queue
    arrow(ax, 11.8, 9.0, 12.6, 9.2, label="enqueue", color="#D93025")
    # API → Redis pub/sub
    arrow(ax, 11.8, 8.0, 12.6, 8.1, label="publish")
    # Queue → workers
    arrow(ax, 13.5, 8.9, 11.8, 4.6, color="#D93025", curve=-0.25,
          label="dequeue", label_pos=0.65, label_offset=(0.4, 0))
    # Redis pub/sub → API pods (fan-out back to clients)
    arrow(ax, 12.6, 7.9, 11.8, 9.2, color="#1A73E8", curve=0.25, ls="--",
          label="SSE fan-out")
    # Workers → rules
    arrow(ax, 9.3, 3.3, 9.3, 3.1)
    # Workers → Postgres
    arrow(ax, 11.8, 2.7, 12.6, 4.3, color="#1A73E8", curve=0.0, label="RLS-scoped writes",
          label_pos=0.55, label_offset=(0, 0.18))
    # API → Postgres
    arrow(ax, 11.8, 8.8, 12.6, 5.0, color="#1A73E8", curve=0.25, ls="--")
    # API → vault
    arrow(ax, 11.8, 6.8, 12.6, 6.9, color="#7627BB", label="KMS / secrets")
    # Workers → object store
    arrow(ax, 11.8, 3.5, 12.6, 3.6, color="#1A73E8", label="presigned · streamed")
    # Workers → LLM gateway
    arrow(ax, 6.8, 3.7, 6.0, 4.5, color="#7627BB", curve=-0.2,
          label="LLM call (gateway)", label_pos=0.5, label_offset=(-0.6, 0.2))
    # LLM gateway → providers
    arrow(ax, 1.9, 4.3, 1.9, 4.1, color="#188038")
    arrow(ax, 4.7, 4.3, 4.7, 4.1, color="#F9AB00")
    # Policy DB → gateway
    arrow(ax, 3.3, 2.9, 3.3, 4.3, color="#D93025", ls=":", label="policy",
          label_offset=(0.4, 0))
    # Workers → Langfuse
    arrow(ax, 9.3, 2.1, 12.6, 2.3, color="#7627BB", label="trace + prompt_version",
          label_pos=0.6, label_offset=(0, 0.18))

    # Legend
    legend_y = 0.7
    ax.add_patch(mpatches.Rectangle((0.4, 0.3), 17.2, 0.9, linewidth=0.5,
                                    edgecolor="#9AA0A6", facecolor="#FFFFFF"))
    ax.text(0.55, legend_y + 0.25, "Legend:", fontsize=8, fontweight="bold")
    samples = [
        ("#1A73E8", "API / data path"),
        ("#188038", "Agent / self-hosted LLM"),
        ("#7627BB", "Pluggable adapter · KMS · trace"),
        ("#F9AB00", "External (regulated boundary)"),
        ("#D93025", "Durable queue / policy"),
    ]
    x_cursor = 1.4
    for color, text in samples:
        ax.add_patch(mpatches.Rectangle((x_cursor, legend_y + 0.15), 0.25, 0.2,
                                        facecolor=color, edgecolor="none"))
        ax.text(x_cursor + 0.32, legend_y + 0.25, text, fontsize=7, va="center")
        x_cursor += 3.3

    out = os.path.join(HERE, "architecture_future.png")
    fig.savefig(out, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


if __name__ == "__main__":
    cur = draw_current()
    fut = draw_future()
    print(f"WROTE: {cur}")
    print(f"WROTE: {fut}")
