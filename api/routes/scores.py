"""
Score endpoints — driver scores and statistics.

Implemented in feature/api-backend.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/scores", tags=["scores"])


@router.get("/overall")
def get_overall_score() -> dict:
    """Return the current overall driver score. Implemented in feature/api-backend."""
    return {"detail": "Not yet implemented"}


@router.get("/history")
def get_score_history() -> dict:
    """Return per-clip score history for trend charts. Implemented in feature/api-backend."""
    return {"detail": "Not yet implemented"}
