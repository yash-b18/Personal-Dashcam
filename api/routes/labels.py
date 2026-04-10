"""
Labeling endpoints — powers the admin clip review interface.

Implemented in feature/api-backend.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/labels", tags=["labels"])


@router.get("/queue")
def get_label_queue() -> dict:
    """Return the next batch of unlabeled clips. Implemented in feature/api-backend."""
    return {"detail": "Not yet implemented"}


@router.post("/{clip_id}")
def submit_label(clip_id: str) -> dict:
    """Submit a thumbs up/down label for a clip. Implemented in feature/api-backend."""
    return {"detail": "Not yet implemented"}
