"""
Video / clip endpoints.

Implemented in feature/api-backend. Stub registered here so the router
structure is in place from project setup.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("")
def list_clips() -> dict:
    """List all clips. Implemented in feature/api-backend."""
    return {"detail": "Not yet implemented"}


@router.get("/{clip_id}")
def get_clip(clip_id: str) -> dict:
    """Get a single clip by ID. Implemented in feature/api-backend."""
    return {"detail": "Not yet implemented"}
