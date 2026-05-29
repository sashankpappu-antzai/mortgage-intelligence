"""mortgage-intelligence — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .core.config import get_settings
from .core.rate_limit import limiter
from .routers import auth, dashboard, documents, health, loans, webhooks

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting mortgage-intelligence ({settings.app_env})")
    yield
    # Shutdown
    logger.info("Shutting down")


def _resolve_cors_origins() -> list[str]:
    if settings.app_env == "dev" and not settings.allowed_origins:
        # Permissive only on a developer laptop, when no explicit list is provided.
        return ["http://localhost:3000", "http://localhost:3100", "http://127.0.0.1:3000"]
    if not settings.allowed_origins:
        # Defence-in-depth: Settings already fails fast on this in non-dev, but in
        # case the validator is bypassed, never fall back to wildcard.
        raise RuntimeError("ALLOWED_ORIGINS must be configured in non-dev environments")
    return settings.allowed_origins


def create_app() -> FastAPI:
    _docs_url = "/docs" if settings.app_env == "dev" else None
    _redoc_url = "/redoc" if settings.app_env == "dev" else None

    app = FastAPI(
        title="Mortgage Intelligence",
        version="0.1.0",
        description="AI-powered mortgage processing platform — Conventional Loans",
        docs_url=_docs_url,
        redoc_url=_redoc_url,
        lifespan=lifespan,
    )

    # Rate limiting (slowapi)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if settings.app_env != "dev":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(loans.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")

    return app


app = create_app()
