"""Async PostgreSQL client — SQLAlchemy engine and session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..core.config import get_settings

settings = get_settings()

_engine = create_async_engine(settings.postgres_url, echo=settings.app_env == "dev")
_SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with _SessionFactory() as session:
        yield session
