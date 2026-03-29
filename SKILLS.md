# SKILLS.md — mortgage-intelligence

> Development reference for AI coding assistants and engineers working in this repo.

---

## Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI (async Python 3.11+) |
| Agent framework | langchain |
| Frontend | nextjs |
| Databases | postgres |
| LLM providers | claude |
| Auth | Azure AD (OAuth2 JWT) |
| Observability | Langfuse |
| Package manager | uv |
| Containerisation | Docker Compose |

---

## Development Commands

```bash
# Backend
uv sync
uv run uvicorn main:app --reload   # starts on :8000

# Run all tests
uv run pytest

# Lint / format
uv run ruff check .
uv run ruff format .

# All services via Docker
docker compose up
docker compose down
```

---

## Key Conventions

1. All Python functions are `async def`. Use `asyncio.run()` only at the top-level entry.
2. Settings are loaded via `get_settings()` (cached). Never read `os.environ` directly.
3. All new agents must extend `BaseAgent` — Langfuse tracing is applied automatically.
4. DB clients are singletons imported from `db/`. Use `get_db()` / `get_neo4j()` etc. as FastAPI dependencies.
5. Never commit `.env.*` files — use `.env.example` as the template.

---

## Adding a New Agent

1. Create `backend/agents/<name>_agent.py`
2. Subclass `BaseAgent`
3. Implement `async def run(self, input: str, session_id: str) -> Any`
4. Register it in the appropriate router

---

## Adding a New API Endpoint

1. Create or edit a file in `backend/routers/`
2. Define an `APIRouter` with a logical prefix and tags
3. Register the router in `backend/main.py` via `app.include_router(...)`
