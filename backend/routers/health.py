"""Health check router."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check() -> dict:
    return {"status": "ok", "service": "mortgage-intelligence"}
