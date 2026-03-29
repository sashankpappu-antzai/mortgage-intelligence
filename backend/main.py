"""mortgage-intelligence — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "dev" else settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(loans.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")

    return app


app = create_app()
