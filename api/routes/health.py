"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check() -> dict:
    """Return API health status."""
    return {"status": "ok", "service": "dashcamiq-api"}
