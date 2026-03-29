# CLAUDE.md — mortgage-intelligence backend

> Read this before writing, editing, or reviewing any backend code in this project.

---

## What This Is

Backend service for **mortgage-intelligence** — a FastAPI application with agentic AI capabilities.

**Stack:**
- Framework: FastAPI (async)
- Agent framework: langchain
- Databases: postgres
- LLM providers: claude
- Auth: Azure AD (OAuth2 JWT)
- Observability: Langfuse
- Package manager: uv

---

## Structure

```
backend/
├── main.py              # FastAPI app factory and lifespan
├── routers/             # API route handlers
├── agents/              # Agent classes extending BaseAgent
│   ├── base_agent.py    # Abstract base with Langfuse tracing
│   └── tools/           # Tool functions used by agents
├── services/            # Business logic layer
├── models/              # Pydantic request/response models
├── db/                  # Database client modules
├── auth/                # Azure AD auth dependency
├── core/
│   └── config.py        # pydantic-settings Settings class
└── tests/
    ├── unit/
    └── evals/
```

---

## Conventions

- All functions must be `async def`
- Use `get_settings()` (cached) everywhere — never read env vars directly
- All new agents must extend `BaseAgent` — Langfuse tracing is automatic
- Use `rich` for any CLI output; use structured logging (`structlog` or standard `logging`) for application logs
- Format with `ruff format`, lint with `ruff check`

---

## Running

```bash
uv sync
uv run uvicorn main:app --reload
uv run pytest
```
